"""Business logic for orders and incoming AI support events."""

import logging

from company_service.repositories import OrderRepository
from company_service.schemas import Order, WebhookEvent

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    pass


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def get_order(self, order_number: str) -> Order:
        order = await self._repository.get(order_number)
        if order is None:
            raise OrderNotFoundError(order_number)
        return order


class WebhookService:
    async def handle(self, event: WebhookEvent) -> None:
        logger.info(
            "Accepted AI support event %s for conversation %s",
            event.event,
            event.conversation_id,
        )

