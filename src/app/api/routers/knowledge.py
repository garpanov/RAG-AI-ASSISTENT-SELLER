"""Admin knowledge document endpoints."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.dependencies import get_knowledge_document_service
from app.api.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentCreated,
    KnowledgeDocumentList,
    KnowledgeDocumentListItem,
    KnowledgeDocumentUpdate,
)
from app.services.document_text import (
    EmptyDocumentFileError,
    InvalidDocumentFileError,
    UnsupportedDocumentFileError,
)
from app.services.knowledge import (
    InvalidKnowledgeDocumentNumberError,
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


@router.post(
    "/documents/upload",
    response_model=KnowledgeDocumentCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    number_document: Annotated[str, Form(min_length=1, max_length=500)],
    file: Annotated[UploadFile, File()],
    service: Annotated[
        KnowledgeDocumentService, Depends(get_knowledge_document_service)
    ],
) -> KnowledgeDocumentCreated:
    try:
        document = await service.create_document_from_file(
            number_document=number_document,
            filename=file.filename or "",
            data=await file.read(),
        )
    except InvalidKnowledgeDocumentNumberError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="number_document must not be blank",
        ) from exc
    except UnsupportedDocumentFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported file types are PDF, DOCX, and TXT",
        ) from exc
    except InvalidDocumentFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded file is invalid or cannot be read",
        ) from exc
    except EmptyDocumentFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded file contains no extractable text",
        ) from exc
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


@router.patch(
    "/documents",
    response_model=KnowledgeDocumentCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def update_document(
    payload: KnowledgeDocumentUpdate,
    service: Annotated[
        KnowledgeDocumentService, Depends(get_knowledge_document_service)
    ],
) -> KnowledgeDocumentCreated:
    try:
        document = await service.update_document(
            number_document=payload.number_document,
            content=payload.content,
        )
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found",
        ) from exc
    except KnowledgeQueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document was updated, but indexing could not be queued",
        ) from exc
    return KnowledgeDocumentCreated.model_validate(document)


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
