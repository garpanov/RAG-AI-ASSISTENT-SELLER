"""HTTP clients for company-owned support integrations."""

from typing import Any
from urllib.parse import quote

import httpx


class OrderClient:
    def __init__(
        self, *, base_url: str, api_key: str, timeout_seconds: float
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def get_order(self, order_number: str) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Orders API is not configured")
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/orders/{quote(order_number, safe='')}",
                headers=headers,
            )
            response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Orders API returned a non-object response")
        return payload


class CompanyWebhookClient:
    def __init__(
        self, *, url: str, secret: str, timeout_seconds: float
    ) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout_seconds

    async def send(self, payload: dict[str, Any]) -> None:
        if not self._url:
            raise RuntimeError("Company webhook is not configured")
        headers = {}
        if self._secret:
            headers["Authorization"] = f"Bearer {self._secret}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, headers=headers, json=payload)
            response.raise_for_status()
