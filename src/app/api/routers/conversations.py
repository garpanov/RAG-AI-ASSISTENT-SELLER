"""Customer conversation message endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.dependencies import get_conversation_message_service
from app.api.schemas import ConversationMessageAccepted, ConversationMessageCreate
from app.services.conversations import (
    ConversationClosedError,
    ConversationMessageService,
    ConversationNotFoundError,
    MessageQueueUnavailableError,
)

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_message(
    conversation_id: Annotated[UUID, Path()],
    payload: ConversationMessageCreate,
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_message_service)
    ],
) -> ConversationMessageAccepted:
    try:
        message = await service.accept(
            conversation_id=conversation_id, content=payload.content
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    except ConversationClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is closed",
        ) from exc
    except MessageQueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message was saved, but processing could not be queued",
        ) from exc
    return ConversationMessageAccepted(message_id=message.id)
