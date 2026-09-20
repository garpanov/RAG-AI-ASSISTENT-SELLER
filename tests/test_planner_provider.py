import json
from typing import Any, Self

import pytest
from pytest import MonkeyPatch

from app.providers.planner import GeminiPlannerProvider, PlannerMessage


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        result = {
            "rewritten_query": "Where is order 12345?",
            "intent": "order_status",
            "confidence": 91,
            "status": "answer",
            "rag": {"required": False, "query": None},
            "tools": {
                "required": True,
                "calls": [
                    {
                        "name": "get_order",
                        "arguments": {"order_number": "12345"},
                    }
                ],
            },
            "handoff": {
                "required": False,
                "possible": True,
                "reason": None,
            },
            "conversation_summary": None,
        }
        return {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(result)}]}}
            ]
        }


class FakeAsyncClient:
    last_url: str | None = None
    last_headers: dict[str, str] | None = None
    last_payload: dict[str, Any] | None = None

    def __init__(self, *, timeout: float) -> None:
        assert timeout == 12.0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        type(self).last_url = url
        type(self).last_headers = headers
        type(self).last_payload = json
        return FakeResponse()


@pytest.mark.asyncio
async def test_gemini_planner_uses_structured_output(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.providers.planner.httpx.AsyncClient", FakeAsyncClient
    )
    provider = GeminiPlannerProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gemini-key",
        model_name="gemini-3.5-flash-lite",
        timeout_seconds=12.0,
    )

    result = await provider.plan(
        messages=[
            PlannerMessage(author="customer", content="Where is order 12345?")
        ],
        previous_summary=None,
        messages_to_summarize=[],
    )

    assert result.intent == "order_status"
    assert result.tools.calls[0].arguments == {"order_number": "12345"}
    assert FakeAsyncClient.last_url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )
    assert FakeAsyncClient.last_headers == {
        "Content-Type": "application/json",
        "x-goog-api-key": "gemini-key",
    }
    assert FakeAsyncClient.last_payload is not None
    generation_config = FakeAsyncClient.last_payload["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"]["type"] == "object"


@pytest.mark.asyncio
async def test_gemini_planner_retries_503_after_ten_seconds(
    monkeypatch: MonkeyPatch,
) -> None:
    responses = [FakeResponseWithStatus(503), FakeResponseWithStatus(200)]
    sleeps: list[float] = []

    async def fake_post(
        _self: object,
        _url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        del headers, json
        return responses.pop(0)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(FakeAsyncClient, "post", fake_post)
    monkeypatch.setattr(
        "app.providers.planner.httpx.AsyncClient", FakeAsyncClient
    )
    monkeypatch.setattr("app.providers.planner.asyncio.sleep", fake_sleep)
    provider = GeminiPlannerProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gemini-key",
        model_name="gemini-3.5-flash-lite",
        timeout_seconds=12.0,
    )

    result = await provider.plan(
        messages=[PlannerMessage(author="customer", content="Hello")],
        previous_summary=None,
        messages_to_summarize=[],
    )

    assert result.intent == "order_status"
    assert sleeps == [10]
    assert responses == []


class FakeResponseWithStatus(FakeResponse):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
