"""Switchable providers for final customer-support responses."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.providers.planner import PlannerMessage


class ResponseProvider(Protocol):
    async def answer(
        self,
        *,
        question: str,
        summary: str | None,
        messages: Sequence[PlannerMessage],
        context: Sequence[str],
        tool_results: Sequence[dict[str, Any]],
    ) -> str: ...


SYSTEM_PROMPT = (
    "You are an English-language customer support assistant. Answer the current "
    "customer question accurately and concisely. Use the supplied FAQ context and "
    "tool results as the only sources for company-specific factual claims. The "
    "summary contains older conversation context and the messages are the latest "
    "10 turns verbatim. If required information is absent, say so; never invent facts."
)


def _request_payload(
    *,
    question: str,
    summary: str | None,
    messages: Sequence[PlannerMessage],
    context: Sequence[str],
    tool_results: Sequence[dict[str, Any]],
) -> str:
    return json.dumps(
        {
            "current_question": question,
            "older_conversation_summary": summary,
            "latest_messages": [message.model_dump() for message in messages],
            "rag_chunks": list(context),
            "tool_results": list(tool_results),
        },
        ensure_ascii=False,
    )


class GeminiResponseProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        model = quote(model_name.removeprefix("models/"), safe="")
        self._url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def answer(
        self,
        *,
        question: str,
        summary: str | None,
        messages: Sequence[PlannerMessage],
        context: Sequence[str],
        tool_results: Sequence[dict[str, Any]],
    ) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _request_payload(
                                question=question,
                                summary=summary,
                                messages=messages,
                                context=context,
                                tool_results=tool_results,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.2},
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                response = await client.post(
                    self._url, headers=headers, json=payload
                )
                if response.status_code != 503:
                    break
                await asyncio.sleep(10)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(_gemini_error_message(response)) from exc
        data: Any = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        answer = "".join(str(part.get("text", "")) for part in parts).strip()
        if not answer:
            raise ValueError("Gemini returned an empty response")
        return answer


class OpenAICompatibleResponseProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model_name = model_name
        self._timeout = timeout_seconds

    async def answer(
        self,
        *,
        question: str,
        summary: str | None,
        messages: Sequence[PlannerMessage],
        context: Sequence[str],
        tool_results: Sequence[dict[str, Any]],
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _request_payload(
                        question=question,
                        summary=summary,
                        messages=messages,
                        context=context,
                        tool_results=tool_results,
                    ),
                },
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, headers=headers, json=payload)
            response.raise_for_status()
        data: Any = response.json()
        answer = str(data["choices"][0]["message"]["content"]).strip()
        if not answer:
            raise ValueError("Response provider returned an empty response")
        return answer


def create_response_provider(settings: Settings) -> ResponseProvider:
    if settings.answer_provider == "gemini":
        return GeminiResponseProvider(
            base_url=settings.answer_base_url,
            api_key=settings.answer_api_key,
            model_name=settings.answer_model_name,
            timeout_seconds=settings.answer_timeout_seconds,
        )
    if settings.answer_provider == "openai_compatible":
        return OpenAICompatibleResponseProvider(
            base_url=settings.answer_base_url,
            api_key=settings.answer_api_key,
            model_name=settings.answer_model_name,
            timeout_seconds=settings.answer_timeout_seconds,
        )
    raise ValueError(f"Unsupported answer provider: {settings.answer_provider}")


def _gemini_error_message(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
        detail = str(payload.get("error", {}).get("message", response.text))
    except ValueError:
        detail = response.text
    return f"Gemini Answer request failed ({response.status_code}): {detail}"
