"""Business logic for accepting and processing customer messages."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.conversations import MessageJobPublisher
from app.models import ConversationStatus, Message, MessageProcessingStatus
from app.providers.embeddings import EmbeddingProvider
from app.providers.integrations import CompanyWebhookClient, OrderClient
from app.providers.planner import PlannerMessage, PlannerProvider, PlannerResult
from app.providers.reranking import RerankerProvider
from app.providers.responses import ResponseProvider
from app.repositories.conversations import ConversationRepository


class ConversationNotFoundError(RuntimeError):
    pass


class ConversationClosedError(RuntimeError):
    pass


class MessageQueueUnavailableError(RuntimeError):
    pass


class ConversationMessageService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: ConversationRepository,
        publisher: MessageJobPublisher,
    ) -> None:
        self._session = session
        self._repository = repository
        self._publisher = publisher

    async def accept(self, *, conversation_id: UUID, content: str) -> Message:
        conversation = await self._repository.get_or_create_conversation(
            conversation_id
        )
        if conversation.status == ConversationStatus.CLOSED:
            raise ConversationClosedError

        message = await self._repository.create_customer_message(
            conversation_id=conversation_id,
            content=content,
        )
        await self._session.commit()
        try:
            await self._publisher.publish(message.id)
        except Exception as exc:
            queued_message = await self._repository.get_message_for_update(message.id)
            if queued_message is not None:
                await self._repository.set_processing_state(
                    queued_message,
                    MessageProcessingStatus.FAILED,
                    error="Could not enqueue message for processing",
                )
                await self._session.commit()
            raise MessageQueueUnavailableError from exc
        return message


class ConversationProcessingService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: ConversationRepository,
        planner: PlannerProvider,
        response_provider: ResponseProvider,
        embedding_provider: EmbeddingProvider,
        reranker: RerankerProvider,
        order_client: OrderClient,
        webhook_client: CompanyWebhookClient,
        rag_top_k: int,
        rag_candidate_k: int,
        handoff_confidence_threshold: int,
    ) -> None:
        self._session = session
        self._repository = repository
        self._planner = planner
        self._response_provider = response_provider
        self._embedding_provider = embedding_provider
        self._reranker = reranker
        self._order_client = order_client
        self._webhook_client = webhook_client
        self._rag_top_k = rag_top_k
        self._rag_candidate_k = rag_candidate_k
        self._handoff_confidence_threshold = handoff_confidence_threshold

    async def process(self, message_id: UUID) -> None:
        message = await self._repository.get_message_for_update(message_id)
        if message is None or message.processing_status != MessageProcessingStatus.PENDING:
            return
        await self._repository.set_processing_state(
            message, MessageProcessingStatus.PROCESSING
        )
        await self._session.commit()

        conversation = await self._repository.get_conversation(
            message.conversation_id
        )
        if conversation is None:
            raise ConversationNotFoundError
        history_records = await self._repository.recent_messages(
            message.conversation_id,
            through_message=message,
            limit=10,
        )
        messages_to_summarize = await self._repository.messages_to_summarize(
            conversation,
            before_message=history_records[0],
        )
        history = [
            PlannerMessage(author=item.author.value, content=item.content)
            for item in history_records
        ]
        summary_messages = [
            PlannerMessage(author=item.author.value, content=item.content)
            for item in messages_to_summarize
        ]
        plan = await self._planner.plan(
            messages=history,
            previous_summary=conversation.summary,
            messages_to_summarize=summary_messages,
        )

        context: list[str] = []
        source_references: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        execution_errors: list[str] = []
        conversation_summary: str | None

        if messages_to_summarize:
            if plan.conversation_summary:
                await self._repository.set_summary(
                    conversation,
                    summary=plan.conversation_summary,
                    through_message_id=messages_to_summarize[-1].id,
                )
                conversation_summary = plan.conversation_summary
            else:
                execution_errors.append("conversation_summary_missing")
                conversation_summary = conversation.summary
        else:
            conversation_summary = conversation.summary

        if plan.rag.required:
            try:
                embeddings = await self._embedding_provider.embed_documents(
                    [message.content]
                )
                chunks = await self._repository.search_knowledge(
                    embeddings[0], limit=self._rag_candidate_k
                )
                ranked_indices = await self._reranker.rank(
                    query=message.content,
                    documents=[chunk.content for chunk in chunks],
                    limit=self._rag_top_k,
                )
                chunks = [chunks[index] for index in ranked_indices]
                context = [chunk.content for chunk in chunks]
                source_references = [
                    {
                        "type": "knowledge_chunk",
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                    }
                    for chunk in chunks
                ]
                if not chunks:
                    execution_errors.append("rag_no_results")
            except Exception:  # noqa: BLE001 - a failed dependency forces handoff
                execution_errors.append("rag_unavailable")

        if plan.tools.required:
            if not plan.tools.calls:
                execution_errors.append("tool_calls_missing")
            for call in plan.tools.calls:
                if call.name != "get_order":
                    execution_errors.append(f"unsupported_tool:{call.name}")
                    continue
                order_number = call.arguments.get("order_number")
                if not isinstance(order_number, str) or not order_number:
                    execution_errors.append("get_order_invalid_arguments")
                    continue
                try:
                    result = await self._order_client.get_order(order_number)
                    tool_results.append(
                        {
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": result,
                        }
                    )
                except Exception:  # noqa: BLE001 - a failed dependency forces handoff
                    execution_errors.append("get_order_failed")

        requires_handoff = self._requires_handoff(
            plan=plan,
            conversation_status=conversation.status,
            execution_errors=execution_errors,
        )
        if requires_handoff:
            await self._finish_handoff(
                message=message,
                plan=plan,
                reason=self._handoff_reason(plan, execution_errors),
                tool_results=tool_results,
                source_references=source_references,
            )
            return

        answer = await self._response_provider.answer(
            question=message.content,
            summary=conversation_summary,
            messages=history,
            context=context,
            tool_results=tool_results,
        )
        response_message = await self._repository.create_assistant_message(
            conversation_id=message.conversation_id,
            content=answer,
            confidence=plan.confidence / 100,
            source_references=source_references,
        )
        await self._repository.set_processing_state(
            message,
            MessageProcessingStatus.COMPLETED,
            plan=plan.model_dump(mode="json"),
        )
        await self._session.commit()
        await self._webhook_client.send(
            {
                "event": "message.response",
                "conversation_id": str(message.conversation_id),
                "in_reply_to_message_id": str(message.id),
                "message": {
                    "id": str(response_message.id),
                    "author": "assistant",
                    "content": response_message.content,
                },
                "confidence": plan.confidence,
                "intent": plan.intent,
                "sources": source_references,
            }
        )

    def _requires_handoff(
        self,
        *,
        plan: PlannerResult,
        conversation_status: ConversationStatus,
        execution_errors: list[str],
    ) -> bool:
        return (
            plan.status == "handoff"
            or plan.handoff.required
            or plan.confidence < self._handoff_confidence_threshold
            or bool(execution_errors)
            or conversation_status
            in {ConversationStatus.WAITING_MANAGER, ConversationStatus.MANAGER}
        )

    @staticmethod
    def _handoff_reason(plan: PlannerResult, execution_errors: list[str]) -> str:
        if execution_errors:
            return execution_errors[0]
        return plan.handoff.reason or plan.intent or "human_judgment_required"

    async def _finish_handoff(
        self,
        *,
        message: Message,
        plan: PlannerResult,
        reason: str,
        tool_results: list[dict[str, Any]],
        source_references: list[dict[str, Any]],
    ) -> None:
        conversation = await self._repository.get_conversation(
            message.conversation_id
        )
        if conversation is None:
            raise ConversationNotFoundError
        handoff = await self._repository.create_handoff(
            conversation, reason=reason
        )
        await self._repository.set_processing_state(
            message,
            MessageProcessingStatus.COMPLETED,
            plan=plan.model_dump(mode="json"),
        )
        await self._session.commit()
        await self._webhook_client.send(
            {
                "event": "conversation.handoff_required",
                "conversation_id": str(message.conversation_id),
                "message_id": str(message.id),
                "handoff_id": str(handoff.id),
                "reason": reason,
                "intent": plan.intent,
                "confidence": plan.confidence,
                "rewritten_query": plan.rewritten_query,
                "tools": tool_results,
                "sources": source_references,
            }
        )

    async def mark_failed(self, message_id: UUID, error: Exception) -> None:
        await self._session.rollback()
        message = await self._repository.get_message_for_update(message_id)
        if message is None:
            return
        await self._repository.set_processing_state(
            message,
            MessageProcessingStatus.FAILED,
            error=str(error)[:2000],
        )
        await self._session.commit()
