"""RabbitMQ consumer that chunks and embeds knowledge documents."""

import asyncio
import json
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.core.config import get_settings
from app.database.session import async_session_factory
from app.providers.embeddings import create_embedding_provider
from app.repositories.knowledge import KnowledgeRepository
from app.services.knowledge import KnowledgeIndexingService, TextChunker


async def run() -> None:
    settings = get_settings()
    embedding_provider = create_embedding_provider(settings)
    chunker = TextChunker(
        chunk_size=settings.knowledge_chunk_size,
        overlap=settings.knowledge_chunk_overlap,
    )
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(
            settings.knowledge_queue_name, durable=True
        )

        async def process(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                payload = json.loads(message.body)
                document_id = UUID(payload["document_id"])
                revision = int(payload["revision"])
                async with async_session_factory() as session:
                    service = KnowledgeIndexingService(
                        session=session,
                        repository=KnowledgeRepository(session),
                        chunker=chunker,
                        embedding_provider=embedding_provider,
                    )
                    await service.index_document(document_id, revision)

        await queue.consume(process)
        await asyncio.Future()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
