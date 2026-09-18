from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.providers.embeddings import EmbeddingProvider
from app.repositories.knowledge import KnowledgeRepository
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentService,
    KnowledgeIndexingService,
    TextChunker,
)


class FakeEmbeddingProvider:
    @property
    def dimensions(self) -> int:
        return 3

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.mark.asyncio
async def test_delete_document_commits() -> None:
    number_document = "DOC-001"
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.delete_document.return_value = True
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = KnowledgeDocumentService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        publisher=publisher,
    )

    await service.delete_document(number_document)

    repository.delete_document.assert_awaited_once_with(number_document)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_document_raises_when_document_does_not_exist() -> None:
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.delete_document.return_value = False
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = KnowledgeDocumentService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        publisher=publisher,
    )

    with pytest.raises(KnowledgeDocumentNotFoundError):
        await service.delete_document("DOC-404")

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_document_raises_when_number_already_exists() -> None:
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.document_exists.return_value = True
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = KnowledgeDocumentService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        publisher=publisher,
    )

    with pytest.raises(KnowledgeDocumentAlreadyExistsError):
        await service.create_document(
            number_document="DOC-001",
            content="Returns policy",
        )

    repository.create_document.assert_not_awaited()
    session.commit.assert_not_awaited()
    publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_document_replaces_content_and_queues_indexing() -> None:
    document = KnowledgeDocument(
        id=uuid4(),
        number_document="DOC-001",
        content="New returns policy",
        status=KnowledgeDocumentStatus.PENDING,
    )
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.update_document.return_value = document
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = KnowledgeDocumentService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        publisher=publisher,
    )

    result = await service.update_document(
        number_document="DOC-001",
        content="New returns policy",
    )

    assert result is document
    repository.update_document.assert_awaited_once_with(
        number_document="DOC-001",
        content="New returns policy",
    )
    session.commit.assert_awaited_once()
    publisher.publish.assert_awaited_once_with(document.id)


@pytest.mark.asyncio
async def test_update_document_raises_when_document_does_not_exist() -> None:
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.update_document.return_value = None
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = KnowledgeDocumentService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        publisher=publisher,
    )

    with pytest.raises(KnowledgeDocumentNotFoundError):
        await service.update_document(
            number_document="DOC-404",
            content="New returns policy",
        )

    session.commit.assert_not_awaited()
    publisher.publish.assert_not_awaited()


def test_chunker_splits_content_with_overlap() -> None:
    chunks = TextChunker(chunk_size=12, overlap=4).split(
        "one two three four five"
    )

    assert len(chunks) > 1
    assert chunks[0] == "one two"
    assert "two" in chunks[1]


@pytest.mark.asyncio
async def test_index_document_embeds_and_replaces_chunks() -> None:
    document = KnowledgeDocument(
        id=uuid4(),
        number_document="Returns",
        content="Returns are accepted within thirty days.",
        status=KnowledgeDocumentStatus.PENDING,
    )
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.get_document_for_update.side_effect = [document, document]
    session = AsyncMock(spec=AsyncSession)
    service = KnowledgeIndexingService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        chunker=TextChunker(chunk_size=100, overlap=10),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
    )

    await service.index_document(document.id)

    repository.set_status.assert_awaited_once_with(
        document, KnowledgeDocumentStatus.PROCESSING
    )
    repository.replace_chunks.assert_awaited_once_with(
        document,
        [
            (
                "Returns are accepted within thirty days.",
                6,
                [1.0, 0.0, 0.0],
            )
        ],
    )
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_index_document_marks_failure() -> None:
    document = KnowledgeDocument(
        id=uuid4(),
        number_document="Empty",
        content="   ",
        status=KnowledgeDocumentStatus.PENDING,
    )
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.get_document_for_update.side_effect = [document, document]
    session = AsyncMock(spec=AsyncSession)
    service = KnowledgeIndexingService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        chunker=TextChunker(chunk_size=100, overlap=10),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
    )

    with pytest.raises(ValueError, match="empty"):
        await service.index_document(document.id)

    repository.set_status.assert_awaited_with(
        document,
        KnowledgeDocumentStatus.FAILED,
        error="Document content is empty after normalization",
    )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_index_document_does_not_replace_chunks_after_content_changes() -> None:
    document_id = uuid4()
    old_document = KnowledgeDocument(
        id=document_id,
        number_document="Returns",
        content="Old returns policy",
        status=KnowledgeDocumentStatus.PENDING,
    )
    updated_document = KnowledgeDocument(
        id=document_id,
        number_document="Returns",
        content="New returns policy",
        status=KnowledgeDocumentStatus.PENDING,
    )
    repository = AsyncMock(spec=KnowledgeRepository)
    repository.get_document_for_update.side_effect = [
        old_document,
        updated_document,
    ]
    session = AsyncMock(spec=AsyncSession)
    service = KnowledgeIndexingService(
        session=cast(AsyncSession, session),
        repository=cast(KnowledgeRepository, repository),
        chunker=TextChunker(chunk_size=100, overlap=10),
        embedding_provider=cast(EmbeddingProvider, FakeEmbeddingProvider()),
    )

    await service.index_document(document_id)

    repository.replace_chunks.assert_not_awaited()
