"""RabbitMQ transport for knowledge indexing jobs."""

from typing import Protocol
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection


class KnowledgeJobPublisher(Protocol):
    async def publish(self, document_id: UUID) -> None: ...


class RabbitMQKnowledgeJobs:
    def __init__(self, *, url: str, queue_name: str) -> None:
        self._url = url
        self.queue_name = queue_name
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self._url)
        channel = await self._connection.channel(publisher_confirms=True)
        await channel.declare_queue(self.queue_name, durable=True)
        self._channel = channel

    async def publish(self, document_id: UUID) -> None:
        await self.connect()
        if self._channel is None:
            raise RuntimeError("RabbitMQ channel is not available")
        message = aio_pika.Message(
            body=str(document_id).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="text/plain",
        )
        await self._channel.default_exchange.publish(
            message, routing_key=self.queue_name
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
