from typing import cast
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_knowledge_document_service
from app.api.routers.knowledge import router
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentService,
)


def create_test_client(service: AsyncMock) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_knowledge_document_service] = (
        lambda: cast(KnowledgeDocumentService, service)
    )
    return TestClient(application)


def test_delete_document_returns_no_content() -> None:
    number_document = "DOC-001"
    service = AsyncMock(spec=KnowledgeDocumentService)

    response = create_test_client(service).delete(
        f"/v1/admin/knowledge/documents/{number_document}"
    )

    assert response.status_code == 204
    assert response.content == b""
    service.delete_document.assert_awaited_once_with(number_document)


def test_delete_document_returns_not_found() -> None:
    number_document = "DOC-404"
    service = AsyncMock(spec=KnowledgeDocumentService)
    service.delete_document.side_effect = KnowledgeDocumentNotFoundError

    response = create_test_client(service).delete(
        f"/v1/admin/knowledge/documents/{number_document}"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge document not found"}


def test_create_document_returns_conflict_for_duplicate_number() -> None:
    service = AsyncMock(spec=KnowledgeDocumentService)
    service.create_document.side_effect = KnowledgeDocumentAlreadyExistsError

    response = create_test_client(service).post(
        "/v1/admin/knowledge/documents",
        json={
            "number_document": "DOC-001",
            "content": "Returns policy",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Knowledge document with this number already exists"
    }
