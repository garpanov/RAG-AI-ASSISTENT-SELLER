from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Conversation,
    ConversationStatus,
    Handoff,
    KnowledgeChunk,
    Message,
    MessageAuthor,
    MessageProcessingStatus,
)
from app.providers.embeddings import EmbeddingProvider
from app.providers.integrations import CompanyWebhookClient, OrderClient
from app.providers.planner import PlannerProvider, PlannerResult
from app.providers.reranking import RerankerProvider
from app.providers.responses import ResponseProvider
from app.repositories.conversations import ConversationRepository
from app.services.conversations import (
    ConversationMessageService,
    ConversationProcessingService,
)


def make_plan(
    *,
    confidence: int = 90,
    status: str = "answer",
    rag_required: bool = False,
    summary: str | None = None,
) -> PlannerResult:
    required = status == "handoff"
    return PlannerResult.model_validate(
        {
            "rewritten_query": "Where is order 12345?",
            "intent": "order_status",
            "confidence": confidence,
            "status": status,
            "rag": {
                "required": rag_required,
                "query": "order delivery policy" if rag_required else None,
            },
            "tools": {"required": False, "calls": []},
            "handoff": {
                "required": required,
                "possible": True,
                "reason": "order_issue" if required else None,
            },
            "conversation_summary": summary,
        }
    )


def make_service(
    repository: AsyncMock,
    session: AsyncMock,
    planner: AsyncMock,
    response_provider: AsyncMock,
    webhook: AsyncMock,
    embedding_provider: AsyncMock | None = None,
    reranker: AsyncMock | None = None,
) -> ConversationProcessingService:
    return ConversationProcessingService(
        session=cast(AsyncSession, session),
        repository=cast(ConversationRepository, repository),
        planner=cast(PlannerProvider, planner),
        response_provider=cast(ResponseProvider, response_provider),
        embedding_provider=cast(
            EmbeddingProvider, embedding_provider or AsyncMock()
        ),
        reranker=cast(RerankerProvider, reranker or AsyncMock()),
        order_client=cast(OrderClient, AsyncMock()),
        webhook_client=cast(CompanyWebhookClient, webhook),
        rag_top_k=5,
        rag_candidate_k=30,
        handoff_confidence_threshold=70,
    )


@pytest.mark.asyncio
async def test_accept_creates_missing_conversation_and_queues_message() -> None:
    conversation_id = uuid4()
    message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="Hello",
        processing_status=MessageProcessingStatus.PENDING,
    )
    conversation = Conversation(id=conversation_id, status=ConversationStatus.BOT)
    repository = AsyncMock(spec=ConversationRepository)
    repository.get_or_create_conversation.return_value = conversation
    repository.create_customer_message.return_value = message
    session = AsyncMock(spec=AsyncSession)
    publisher = AsyncMock()
    service = ConversationMessageService(
        session=cast(AsyncSession, session),
        repository=cast(ConversationRepository, repository),
        publisher=publisher,
    )

    result = await service.accept(
        conversation_id=conversation_id,
        content="Hello",
    )

    assert result is message
    repository.get_or_create_conversation.assert_awaited_once_with(
        conversation_id
    )
    repository.create_customer_message.assert_awaited_once_with(
        conversation_id=conversation_id,
        content="Hello",
    )
    session.commit.assert_awaited_once()
    publisher.publish.assert_awaited_once_with(message.id)


@pytest.mark.asyncio
async def test_processor_uses_recent_history_and_sends_answer() -> None:
    conversation_id = uuid4()
    incoming = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="Where is it?",
        processing_status=MessageProcessingStatus.PENDING,
    )
    earlier = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="My order is 12345",
    )
    conversation = Conversation(id=conversation_id, status=ConversationStatus.BOT)
    response = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.ASSISTANT,
        content="Your order is in transit.",
    )
    repository = AsyncMock(spec=ConversationRepository)
    repository.get_message_for_update.return_value = incoming
    repository.get_conversation.return_value = conversation
    repository.recent_messages.return_value = [earlier, incoming]
    repository.create_assistant_message.return_value = response
    session = AsyncMock(spec=AsyncSession)
    planner = AsyncMock()
    planner.plan.return_value = make_plan()
    response_provider = AsyncMock()
    response_provider.answer.return_value = response.content
    webhook = AsyncMock()
    repository.messages_to_summarize.return_value = []
    service = make_service(
        repository, session, planner, response_provider, webhook
    )

    await service.process(incoming.id)

    repository.recent_messages.assert_awaited_once_with(
        conversation_id, through_message=incoming, limit=10
    )
    history = planner.plan.await_args.kwargs["messages"]
    assert [item.content for item in history] == [
        "My order is 12345",
        "Where is it?",
    ]
    repository.create_assistant_message.assert_awaited_once_with(
        conversation_id=conversation_id,
        content=response.content,
        confidence=0.9,
        source_references=[],
    )
    payload: dict[str, Any] = webhook.send.await_args.args[0]
    assert payload["event"] == "message.response"


@pytest.mark.asyncio
async def test_low_confidence_forces_manager_handoff() -> None:
    conversation_id = uuid4()
    incoming = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="Something is wrong with my payment",
        processing_status=MessageProcessingStatus.PENDING,
    )
    conversation = Conversation(id=conversation_id, status=ConversationStatus.BOT)
    handoff = Handoff(
        id=uuid4(),
        conversation_id=conversation_id,
        reason="order_status",
    )
    repository = AsyncMock(spec=ConversationRepository)
    repository.get_message_for_update.return_value = incoming
    repository.get_conversation.return_value = conversation
    repository.recent_messages.return_value = [incoming]
    repository.create_handoff.return_value = handoff
    session = AsyncMock(spec=AsyncSession)
    planner = AsyncMock()
    planner.plan.return_value = make_plan(confidence=45)
    response_provider = AsyncMock()
    webhook = AsyncMock()
    repository.messages_to_summarize.return_value = []
    service = make_service(
        repository, session, planner, response_provider, webhook
    )

    await service.process(incoming.id)

    repository.create_handoff.assert_awaited_once_with(
        conversation, reason="order_status"
    )
    response_provider.answer.assert_not_awaited()
    payload: dict[str, Any] = webhook.send.await_args.args[0]
    assert payload["event"] == "conversation.handoff_required"
    assert payload["confidence"] == 45


@pytest.mark.asyncio
async def test_processor_incrementally_updates_old_message_summary() -> None:
    conversation_id = uuid4()
    old_message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="My order number is 12345.",
    )
    incoming = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="When will it arrive?",
        processing_status=MessageProcessingStatus.PENDING,
    )
    conversation = Conversation(
        id=conversation_id,
        status=ConversationStatus.BOT,
        summary="The customer placed an order.",
    )
    response = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.ASSISTANT,
        content="I do not have a delivery estimate.",
    )
    repository = AsyncMock(spec=ConversationRepository)
    repository.get_message_for_update.return_value = incoming
    repository.get_conversation.return_value = conversation
    repository.recent_messages.return_value = [incoming]
    repository.messages_to_summarize.return_value = [old_message]
    repository.create_assistant_message.return_value = response
    session = AsyncMock(spec=AsyncSession)
    planner = AsyncMock()
    planner.plan.return_value = make_plan(
        summary="The customer placed order 12345."
    )
    response_provider = AsyncMock()
    response_provider.answer.return_value = response.content
    webhook = AsyncMock()
    service = make_service(
        repository, session, planner, response_provider, webhook
    )

    await service.process(incoming.id)

    planner.plan.assert_awaited_once()
    assert planner.plan.await_args.kwargs["previous_summary"] == (
        "The customer placed an order."
    )
    assert planner.plan.await_args.kwargs["messages_to_summarize"][0].content == (
        "My order number is 12345."
    )
    repository.set_summary.assert_awaited_once_with(
        conversation,
        summary="The customer placed order 12345.",
        through_message_id=old_message.id,
    )
    assert response_provider.answer.await_args.kwargs["summary"] == (
        "The customer placed order 12345."
    )


@pytest.mark.asyncio
async def test_rag_retrieves_30_candidates_and_passes_top_5_to_answer() -> None:
    conversation_id = uuid4()
    incoming = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.CUSTOMER,
        content="What is your delivery policy?",
        processing_status=MessageProcessingStatus.PENDING,
    )
    conversation = Conversation(id=conversation_id, status=ConversationStatus.BOT)
    chunks = [
        KnowledgeChunk(
            id=uuid4(),
            document_id=uuid4(),
            chunk_index=index,
            content=f"Chunk {index}",
            embedding=[0.0] * 384,
        )
        for index in range(30)
    ]
    response = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        author=MessageAuthor.ASSISTANT,
        content="Delivery normally takes three days.",
    )
    repository = AsyncMock(spec=ConversationRepository)
    repository.get_message_for_update.return_value = incoming
    repository.get_conversation.return_value = conversation
    repository.recent_messages.return_value = [incoming]
    repository.messages_to_summarize.return_value = []
    repository.search_knowledge.return_value = chunks
    repository.create_assistant_message.return_value = response
    session = AsyncMock(spec=AsyncSession)
    planner = AsyncMock()
    planner.plan.return_value = make_plan(rag_required=True)
    response_provider = AsyncMock()
    response_provider.answer.return_value = response.content
    embedding_provider = AsyncMock()
    embedding_provider.embed_documents.return_value = [[0.1] * 384]
    reranker = AsyncMock()
    reranker.rank.return_value = [29, 28, 27, 26, 25]
    webhook = AsyncMock()
    service = make_service(
        repository,
        session,
        planner,
        response_provider,
        webhook,
        embedding_provider,
        reranker,
    )

    await service.process(incoming.id)

    embedding_provider.embed_documents.assert_awaited_once_with(
        [incoming.content]
    )
    repository.search_knowledge.assert_awaited_once_with(
        [0.1] * 384, limit=30
    )
    reranker.rank.assert_awaited_once_with(
        query=incoming.content,
        documents=[f"Chunk {index}" for index in range(30)],
        limit=5,
    )
    assert response_provider.answer.await_args.kwargs["context"] == [
        "Chunk 29",
        "Chunk 28",
        "Chunk 27",
        "Chunk 26",
        "Chunk 25",
    ]
