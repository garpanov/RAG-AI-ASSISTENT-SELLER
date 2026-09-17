from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.providers.embeddings import EmbeddingProvider
from app.repositories.knowledge import KnowledgeRepository
from app.services.knowledge import KnowledgeIndexingService, TextChunker


class FakeEmbeddingProvider:
    @property
    def dimensions(self) -> int:
        return 3

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


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
        title="Returns",
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
        title="Empty",
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
