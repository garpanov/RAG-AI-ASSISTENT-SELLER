"""Dependency wiring for the standalone application."""

import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from company_service.config import Settings, get_settings
from company_service.repositories import OrderRepository
from company_service.services import OrderService, WebhookService


@lru_cache
def get_order_service() -> OrderService:
    return OrderService(OrderRepository())


@lru_cache
def get_webhook_service() -> WebhookService:
    return WebhookService()


def _verify_bearer(authorization: str | None, expected: str) -> None:
    supplied = ""
    if authorization is not None and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_orders_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _verify_bearer(authorization, settings.orders_api_key)


def verify_webhook_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _verify_bearer(authorization, settings.webhook_secret)
