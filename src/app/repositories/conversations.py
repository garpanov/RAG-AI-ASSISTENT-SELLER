"""Database access for conversations and message processing."""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    ConversationStatus,
    Handoff,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    Message,
    MessageAuthor,
    MessageProcessingStatus,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return await self._session.get(Conversation, conversation_id)

    async def get_or_create_conversation(
        self, conversation_id: UUID
    ) -> Conversation:
        await self._session.execute(
            insert(Conversation)
            .values(id=conversation_id, status=ConversationStatus.BOT)
            .on_conflict_do_nothing(index_elements=[Conversation.id])
        )
        conversation = await self.get_conversation(conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation could not be created")
        return conversation

    async def create_customer_message(
        self, *, conversation_id: UUID, content: str
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            author=MessageAuthor.CUSTOMER,
            content=content,
            processing_status=MessageProcessingStatus.PENDING,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_message_for_update(self, message_id: UUID) -> Message | None:
        result = await self._session.execute(
            select(Message).where(Message.id == message_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def recent_messages(
        self,
        conversation_id: UUID,
        *,
        through_message: Message,
        limit: int,
    ) -> list[Message]:
        result = await self._session.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                or_(
                    Message.created_at < through_message.created_at,
                    and_(
                        Message.created_at == through_message.created_at,
                        Message.id <= through_message.id,
                    ),
                ),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(reversed(result.all()))

    async def messages_to_summarize(
        self,
        conversation: Conversation,
        *,
        before_message: Message,
    ) -> list[Message]:
        conditions: list[Any] = [
            Message.conversation_id == conversation.id,
            or_(
                Message.created_at < before_message.created_at,
                and_(
                    Message.created_at == before_message.created_at,
                    Message.id < before_message.id,
                ),
            ),
        ]
        if conversation.summary_through_message_id is not None:
            marker = await self._session.get(
                Message, conversation.summary_through_message_id
            )
            if marker is not None:
                conditions.append(
                    or_(
                        Message.created_at > marker.created_at,
                        and_(
                            Message.created_at == marker.created_at,
                            Message.id > marker.id,
                        ),
                    )
                )
        result = await self._session.scalars(
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.all())

    async def set_summary(
        self,
        conversation: Conversation,
        *,
        summary: str,
        through_message_id: UUID,
    ) -> None:
        conversation.summary = summary
        conversation.summary_through_message_id = through_message_id
        await self._session.flush()

    async def search_knowledge(
        self, embedding: list[float], *, limit: int
    ) -> list[KnowledgeChunk]:
        distance = KnowledgeChunk.embedding.cosine_distance(embedding)
        result = await self._session.scalars(
            select(KnowledgeChunk)
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.status == KnowledgeDocumentStatus.READY)
            .order_by(distance)
            .limit(limit)
        )
        return list(result.all())

    async def create_assistant_message(
        self,
        *,
        conversation_id: UUID,
        content: str,
        confidence: float,
        source_references: list[dict[str, Any]],
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            author=MessageAuthor.ASSISTANT,
            content=content,
            confidence=confidence,
            source_references=source_references,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def create_handoff(
        self, conversation: Conversation, *, reason: str
    ) -> Handoff:
        handoff = Handoff(conversation_id=conversation.id, reason=reason)
        conversation.status = ConversationStatus.WAITING_MANAGER
        self._session.add(handoff)
        await self._session.flush()
        return handoff

    async def set_processing_state(
        self,
        message: Message,
        status: MessageProcessingStatus,
        *,
        plan: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        message.processing_status = status
        if plan is not None:
            message.planner_result = plan
        message.processing_error = error
        await self._session.flush()
