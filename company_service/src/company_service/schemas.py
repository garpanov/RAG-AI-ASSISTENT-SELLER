"""HTTP and domain schemas owned by the example company."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    sku: str
    name: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)


class Order(BaseModel):
    order_number: str
    name: str
    items: list[OrderItem]
    total_price: float = Field(ge=0)
    currency: str
    created_at: datetime
    status: Literal["processing", "shipped", "delivered", "cancelled"]
    shipped_at: datetime | None
    tracking_number: str | None


class MessageResponseEvent(BaseModel):
    event: Literal["message.response"]
    conversation_id: UUID
    in_reply_to_message_id: UUID
    message: dict[str, object]
    confidence: int = Field(ge=0, le=100)
    intent: str
    sources: list[dict[str, object]]


class HandoffRequiredEvent(BaseModel):
    event: Literal["conversation.handoff_required"]
    conversation_id: UUID
    message_id: UUID
    handoff_id: UUID
    reason: str
    intent: str
    confidence: int = Field(ge=0, le=100)
    rewritten_query: str
    tools: list[dict[str, object]]
    sources: list[dict[str, object]]


WebhookEvent = Annotated[
    MessageResponseEvent | HandoffRequiredEvent,
    Field(discriminator="event"),
]


class WebhookAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"

