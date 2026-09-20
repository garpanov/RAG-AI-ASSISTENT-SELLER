"""RabbitMQ consumer for planning and answering customer messages."""

import asyncio
import json
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.core.config import get_settings
from app.database.session import async_session_factory
from app.providers.embeddings import EmbeddingProvider, create_embedding_provider
from app.providers.integrations import CompanyWebhookClient, OrderClient
from app.providers.planner import create_planner_provider
from app.providers.reranking import create_reranker_provider
from app.providers.responses import create_response_provider
from app.repositories.conversations import ConversationRepository
from app.services.conversations import ConversationProcessingService


async def run(embedding_provider: EmbeddingProvider | None = None) -> None:
    settings = get_settings()
    planner = create_planner_provider(settings)
    response_provider = create_response_provider(settings)
    reranker = create_reranker_provider(settings)
    embedding_provider = embedding_provider or create_embedding_provider(settings)
    order_client = OrderClient(
        base_url=settings.orders_base_url,
        api_key=settings.orders_api_key,
        timeout_seconds=settings.integration_timeout_seconds,
    )
    webhook_client = CompanyWebhookClient(
        url=settings.company_webhook_url,
        secret=settings.company_webhook_secret,
        timeout_seconds=settings.integration_timeout_seconds,
    )
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(
            settings.message_queue_name, durable=True
        )

        async def process(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                payload = json.loads(message.body)
                message_id = UUID(payload["message_id"])
                async with async_session_factory() as session:
                    service = ConversationProcessingService(
                        session=session,
                        repository=ConversationRepository(session),
                        planner=planner,
                        response_provider=response_provider,
                        embedding_provider=embedding_provider,
                        reranker=reranker,
                        order_client=order_client,
                        webhook_client=webhook_client,
                        rag_top_k=settings.rag_top_k,
                        rag_candidate_k=settings.rag_candidate_k,
                        handoff_confidence_threshold=(
                            settings.planner_handoff_confidence_threshold
                        ),
                    )
                    try:
                        await service.process(message_id)
                    except Exception as exc:  # noqa: BLE001 - persist worker failure
                        await service.mark_failed(message_id, exc)

        await queue.consume(process)
        await asyncio.Future()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
