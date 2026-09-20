"""Thin HTTP routes for the company integration contract."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from company_service.dependencies import (
    get_order_service,
    get_webhook_service,
    verify_orders_token,
    verify_webhook_token,
)
from company_service.schemas import Order, WebhookAccepted, WebhookEvent
from company_service.services import (
    OrderNotFoundError,
    OrderService,
    WebhookService,
)

router = APIRouter()


@router.get(
    "/orders/{order_number}",
    response_model=Order,
    dependencies=[Depends(verify_orders_token)],
)
async def get_order(
    order_number: Annotated[str, Path(min_length=1, max_length=100)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> Order:
    try:
        return await service.get_order(order_number)
    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        ) from exc


@router.post(
    "/webhooks/ai-support",
    response_model=WebhookAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_webhook_token)],
)
async def receive_ai_support_event(
    event: WebhookEvent,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> WebhookAccepted:
    await service.handle(event)
    return WebhookAccepted()

