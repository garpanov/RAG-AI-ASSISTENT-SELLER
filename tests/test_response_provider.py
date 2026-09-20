from typing import Any, ClassVar, Self

import pytest
from pytest import MonkeyPatch

from app.providers.responses import GeminiResponseProvider


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {
            "candidates": [
                {"content": {"parts": [{"text": "The answer"}]}}
            ]
        }


class FakeAsyncClient:
    responses: ClassVar[list[FakeResponse]] = [
        FakeResponse(503),
        FakeResponse(200),
    ]

    def __init__(self, *, timeout: float) -> None:
        assert timeout == 12.0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def post(
        self,
        _url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        del headers, json
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_gemini_response_retries_503_after_ten_seconds(
    monkeypatch: MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    FakeAsyncClient.responses = [FakeResponse(503), FakeResponse(200)]
    monkeypatch.setattr(
        "app.providers.responses.httpx.AsyncClient", FakeAsyncClient
    )
    monkeypatch.setattr("app.providers.responses.asyncio.sleep", fake_sleep)
    provider = GeminiResponseProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gemini-key",
        model_name="gemini-3.6-flash",
        timeout_seconds=12.0,
    )

    answer = await provider.answer(
        question="Hello",
        summary=None,
        messages=[],
        context=[],
        tool_results=[],
    )

    assert answer == "The answer"
    assert sleeps == [10]
    assert FakeAsyncClient.responses == []
