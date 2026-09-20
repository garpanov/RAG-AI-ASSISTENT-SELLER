"""FastAPI dependencies for application services."""

from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.messaging.conversations import RabbitMQMessageJobs
from app.messaging.knowledge import RabbitMQKnowledgeJobs
from app.repositories.conversations import ConversationRepository
from app.repositories.knowledge import KnowledgeRepository
from app.services.conversations import ConversationMessageService
from app.services.knowledge import KnowledgeDocumentService


def get_knowledge_jobs(request: Request) -> RabbitMQKnowledgeJobs:
    return cast(RabbitMQKnowledgeJobs, request.app.state.knowledge_jobs)


def get_message_jobs(request: Request) -> RabbitMQMessageJobs:
    return cast(RabbitMQMessageJobs, request.app.state.message_jobs)


def get_conversation_message_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    publisher: Annotated[RabbitMQMessageJobs, Depends(get_message_jobs)],
) -> ConversationMessageService:
    return ConversationMessageService(
        session=session,
        repository=ConversationRepository(session),
        publisher=publisher,
    )


def get_knowledge_document_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    publisher: Annotated[
        RabbitMQKnowledgeJobs, Depends(get_knowledge_jobs)
    ],
) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        session=session,
        repository=KnowledgeRepository(session),
        publisher=publisher,
    )
