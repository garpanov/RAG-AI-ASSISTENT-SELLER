from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_conversation_message_service
from app.api.routers.conversations import router
from app.models import Message, MessageAuthor, MessageProcessingStatus
from app.services.conversations import (
    ConversationMessageService,
    ConversationNotFoundError,
)


def create_test_client(service: AsyncMock) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_conversation_message_service] = (
        lambda: cast(ConversationMessageService, service)
    )
    return TestClient(application)


def test_create_message_returns_processing() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    service = AsyncMock(spec=ConversationMessageService)
    service.accept.return_value = Message(
        id=message_id,
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="Where is order 12345?",
        processing_status=MessageProcessingStatus.PENDING,
    )

    response = create_test_client(service).post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"content": "  Where is order 12345?  "},
    )

    assert response.status_code == 202
    assert response.json() == {
        "message_id": str(message_id),
        "status": "processing",
    }
    service.accept.assert_awaited_once_with(
        conversation_id=conversation_id,
        content="Where is order 12345?",
    )


def test_create_message_returns_not_found() -> None:
    conversation_id = uuid4()
    service = AsyncMock(spec=ConversationMessageService)
    service.accept.side_effect = ConversationNotFoundError

    response = create_test_client(service).post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"content": "Hello"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}
