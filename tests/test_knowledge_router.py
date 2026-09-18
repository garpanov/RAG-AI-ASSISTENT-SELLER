from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_knowledge_document_service
from app.api.routers.knowledge import router
from app.services.knowledge import (
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
    document_id = uuid4()
    service = AsyncMock(spec=KnowledgeDocumentService)

    response = create_test_client(service).delete(
        f"/v1/admin/knowledge/documents/{document_id}"
    )

    assert response.status_code == 204
    assert response.content == b""
    service.delete_document.assert_awaited_once_with(document_id)


def test_delete_document_returns_not_found() -> None:
    document_id = uuid4()
    service = AsyncMock(spec=KnowledgeDocumentService)
    service.delete_document.side_effect = KnowledgeDocumentNotFoundError

    response = create_test_client(service).delete(
        f"/v1/admin/knowledge/documents/{document_id}"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge document not found"}
