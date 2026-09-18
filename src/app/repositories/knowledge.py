"""Database access for knowledge documents and chunks."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentStatus


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self, *, number_document: str, content: str
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(number_document=number_document, content=content)
        self._session.add(document)
        await self._session.flush()
        return document

    async def document_exists(self, number_document: str) -> bool:
        document_id = await self._session.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.number_document == number_document
            )
        )
        return document_id is not None

    async def update_document(
        self, *, number_document: str, content: str
    ) -> KnowledgeDocument | None:
        result = await self._session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.number_document == number_document)
            .with_for_update()
        )
        document = result.scalar_one_or_none()
        if document is None:
            return None

        await self._session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id
            )
        )
        document.content = content
        document.revision += 1
        document.status = KnowledgeDocumentStatus.PENDING
        document.indexing_error = None
        await self._session.flush()
        return document

    async def list_documents(
        self, *, limit: int, offset: int
    ) -> tuple[list[tuple[KnowledgeDocument, int]], int]:
        chunk_count = (
            select(func.count(KnowledgeChunk.id))
            .where(KnowledgeChunk.document_id == KnowledgeDocument.id)
            .correlate(KnowledgeDocument)
            .scalar_subquery()
        )
        rows = await self._session.execute(
            select(KnowledgeDocument, chunk_count.label("chunk_count"))
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.scalar(select(func.count(KnowledgeDocument.id)))
        return [(document, count) for document, count in rows.all()], total or 0

    async def delete_document(self, number_document: str) -> bool:
        result = await self._session.execute(
            delete(KnowledgeDocument)
            .where(KnowledgeDocument.number_document == number_document)
            .returning(KnowledgeDocument.id)
        )
        return result.scalar_one_or_none() is not None

    async def get_document_for_update(
        self, document_id: UUID
    ) -> KnowledgeDocument | None:
        result = await self._session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def set_status(
        self,
        document: KnowledgeDocument,
        status: KnowledgeDocumentStatus,
        *,
        error: str | None = None,
    ) -> None:
        document.status = status
        document.indexing_error = error
        await self._session.flush()

    async def replace_chunks(
        self,
        document: KnowledgeDocument,
        chunks: list[tuple[str, int, list[float]]],
    ) -> None:
        await self._session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id
            )
        )
        self._session.add_all(
            [
                KnowledgeChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    token_count=token_count,
                    embedding=embedding,
                )
                for index, (content, token_count, embedding) in enumerate(chunks)
            ]
        )
        await self.set_status(document, KnowledgeDocumentStatus.READY)
