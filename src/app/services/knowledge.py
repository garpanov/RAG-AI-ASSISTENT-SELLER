"""Business logic for knowledge documents."""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.knowledge import KnowledgeJobPublisher
from app.models import KnowledgeDocument, KnowledgeDocumentStatus
from app.providers.embeddings import EmbeddingProvider
from app.repositories.knowledge import KnowledgeRepository


class KnowledgeQueueUnavailableError(RuntimeError):
    pass


class KnowledgeDocumentNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentListEntry:
    document: KnowledgeDocument
    chunk_count: int


class TextChunker:
    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and greater than overlap")
        self._chunk_size = chunk_size
        self._overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self._chunk_size, len(normalized))
            if end < len(normalized):
                boundary = normalized.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(normalized):
                break
            start = max(end - self._overlap, start + 1)
        return chunks


class KnowledgeDocumentService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: KnowledgeRepository,
        publisher: KnowledgeJobPublisher,
    ) -> None:
        self._session = session
        self._repository = repository
        self._publisher = publisher

    async def create_document(
        self, *, title: str, content: str, source: str | None
    ) -> KnowledgeDocument:
        document = await self._repository.create_document(
            title=title, content=content, source=source
        )
        await self._session.commit()
        try:
            await self._publisher.publish(document.id)
        except Exception as exc:
            failed_document = await self._repository.get_document_for_update(
                document.id
            )
            if failed_document is not None:
                await self._repository.set_status(
                    failed_document,
                    KnowledgeDocumentStatus.FAILED,
                    error="Could not enqueue document for indexing",
                )
                await self._session.commit()
            raise KnowledgeQueueUnavailableError from exc
        return document

    async def list_documents(
        self, *, limit: int, offset: int
    ) -> tuple[list[DocumentListEntry], int]:
        rows, total = await self._repository.list_documents(
            limit=limit, offset=offset
        )
        return [DocumentListEntry(*row) for row in rows], total

    async def delete_document(self, document_id: UUID) -> None:
        if not await self._repository.delete_document(document_id):
            raise KnowledgeDocumentNotFoundError
        await self._session.commit()


class KnowledgeIndexingService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: KnowledgeRepository,
        chunker: TextChunker,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._session = session
        self._repository = repository
        self._chunker = chunker
        self._embedding_provider = embedding_provider

    async def index_document(self, document_id: UUID) -> None:
        document = await self._repository.get_document_for_update(document_id)
        if document is None:
            return
        await self._repository.set_status(
            document, KnowledgeDocumentStatus.PROCESSING
        )
        await self._session.commit()

        try:
            chunks = self._chunker.split(document.content)
            if not chunks:
                raise ValueError("Document content is empty after normalization")
            embeddings = await self._embedding_provider.embed_documents(chunks)
            if len(embeddings) != len(chunks):
                raise ValueError("Embedding provider returned an invalid batch")
            if any(
                len(embedding) != self._embedding_provider.dimensions
                for embedding in embeddings
            ):
                raise ValueError("Embedding provider returned an invalid dimension")

            document = await self._repository.get_document_for_update(document_id)
            if document is None:
                return
            await self._repository.replace_chunks(
                document,
                [
                    (chunk, len(chunk.split()), embedding)
                    for chunk, embedding in zip(chunks, embeddings, strict=True)
                ],
            )
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            document = await self._repository.get_document_for_update(document_id)
            if document is not None:
                await self._repository.set_status(
                    document,
                    KnowledgeDocumentStatus.FAILED,
                    error=str(exc)[:2000],
                )
                await self._session.commit()
            raise
