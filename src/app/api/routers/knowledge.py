"""Admin knowledge document endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.api.dependencies import get_knowledge_document_service
from app.api.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentCreated,
    KnowledgeDocumentList,
    KnowledgeDocumentListItem,
)
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentService,
    KnowledgeQueueUnavailableError,
)

router = APIRouter(prefix="/v1/admin/knowledge", tags=["admin-knowledge"])


@router.post(
    "/documents",
    response_model=KnowledgeDocumentCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document(
    payload: KnowledgeDocumentCreate,
    service: Annotated[
        KnowledgeDocumentService, Depends(get_knowledge_document_service)
    ],
) -> KnowledgeDocumentCreated:
    try:
        document = await service.create_document(
            number_document=payload.number_document,
            content=payload.content,
            source=payload.source,
        )
    except KnowledgeDocumentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge document with this number already exists",
        ) from exc
    except KnowledgeQueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document was saved, but indexing could not be queued",
        ) from exc
    return KnowledgeDocumentCreated.model_validate(document)


@router.get("/documents", response_model=KnowledgeDocumentList)
async def list_documents(
    service: Annotated[
        KnowledgeDocumentService, Depends(get_knowledge_document_service)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeDocumentList:
    entries, total = await service.list_documents(limit=limit, offset=offset)
    return KnowledgeDocumentList(
        items=[
            KnowledgeDocumentListItem(
                id=entry.document.id,
                number_document=entry.document.number_document,
                source=entry.document.source,
                status=entry.document.status,
                created_at=entry.document.created_at,
                updated_at=entry.document.updated_at,
                chunk_count=entry.chunk_count,
                indexing_error=entry.document.indexing_error,
            )
            for entry in entries
        ],
        total=total,
    )


@router.delete(
    "/documents/{number_document}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    number_document: Annotated[str, Path(min_length=1, max_length=500)],
    service: Annotated[
        KnowledgeDocumentService, Depends(get_knowledge_document_service)
    ],
) -> Response:
    try:
        await service.delete_document(number_document)
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
