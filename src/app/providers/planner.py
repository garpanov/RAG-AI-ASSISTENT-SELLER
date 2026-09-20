"""Switchable LLM provider used by the conversation worker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any, Literal, Protocol
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings


class PlannerMessage(BaseModel):
    author: Literal["customer", "assistant", "manager"]
    content: str


class RagPlan(BaseModel):
    required: bool
    query: str | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolsPlan(BaseModel):
    required: bool
    calls: list[ToolCall] = Field(default_factory=list)


class HandoffPlan(BaseModel):
    required: bool
    possible: bool
    reason: str | None = None


class PlannerResult(BaseModel):
    rewritten_query: str
    intent: str
    confidence: int = Field(ge=0, le=100)
    status: Literal["answer", "handoff"]
    rag: RagPlan
    tools: ToolsPlan
    handoff: HandoffPlan
    conversation_summary: str | None = None


class PlannerProvider(Protocol):
    async def plan(
        self,
        *,
        messages: Sequence[PlannerMessage],
        previous_summary: str | None,
        messages_to_summarize: Sequence[PlannerMessage],
    ) -> PlannerResult: ...


PLANNER_SYSTEM_PROMPT = """You are the planning component of an English-language customer support system.
Use the conversation to rewrite the customer's latest request as a standalone English query and classify it.
Return JSON only, matching the supplied schema.

Rules:
- confidence is an integer from 0 to 100 describing confidence that an accurate answer can be produced.
- status is "handoff" when the issue requires human judgment, concerns a payment/financial dispute, an order problem, safety, legal concerns, or cannot be answered accurately from FAQ/order data. Otherwise use "answer".
- RAG contains FAQ and support materials. Set rag.required when those materials are useful, and provide a standalone English search query.
- The only available tool is get_order with arguments {"order_number": "..."}. Never invent an order number. Use it only when an order number appears in the conversation and order data is relevant.
- handoff.required must agree with status. handoff.possible indicates whether handing off is operationally appropriate. Supply a short snake_case reason when required.
- Keep intent and handoff reason in snake_case.
- conversation_summary is a compact rolling summary of messages older than the latest 10. If messages_to_summarize is non-empty, merge only their durable facts into previous_summary. Keep order numbers, decisions, unresolved issues, and promises. Do not add facts. Keep it under 1200 characters. If there is no previous summary and nothing to summarize, return null.
"""


def _planner_input(
    *,
    messages: Sequence[PlannerMessage],
    previous_summary: str | None,
    messages_to_summarize: Sequence[PlannerMessage],
) -> str:
    request = {
        "previous_summary": previous_summary,
        "messages_to_summarize": [
            message.model_dump() for message in messages_to_summarize
        ],
        "latest_messages": [message.model_dump() for message in messages],
    }
    return json.dumps(request, ensure_ascii=False)


class GeminiPlannerProvider:
    """Planner adapter for Gemini generateContent structured output."""

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

    async def plan(
        self,
        *,
        messages: Sequence[PlannerMessage],
        previous_summary: str | None,
        messages_to_summarize: Sequence[PlannerMessage],
    ) -> PlannerResult:
        payload = {
            "systemInstruction": {
                "parts": [{"text": PLANNER_SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _planner_input(
                                messages=messages,
                                previous_summary=previous_summary,
                                messages_to_summarize=messages_to_summarize,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": PlannerResult.model_json_schema(),
            },
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
                raise RuntimeError(
                    _gemini_error_message(response, component="Planner")
                ) from exc
        data: Any = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        content = "".join(str(part.get("text", "")) for part in parts).strip()
        if not content:
            raise ValueError("Gemini returned an empty planner response")
        return PlannerResult.model_validate_json(content)


class OpenAICompatiblePlannerProvider:
    """Planner adapter for APIs implementing OpenAI chat completions."""

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

    async def _complete(
        self, messages: list[dict[str, str]], *, json_output: bool
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": 0,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])

    async def plan(
        self,
        *,
        messages: Sequence[PlannerMessage],
        previous_summary: str | None,
        messages_to_summarize: Sequence[PlannerMessage],
    ) -> PlannerResult:
        schema = json.dumps(PlannerResult.model_json_schema(), separators=(",", ":"))
        content = await self._complete(
            [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"JSON schema: {schema}\nInput: "
                        f"{_planner_input(messages=messages, previous_summary=previous_summary, messages_to_summarize=messages_to_summarize)}"
                    ),
                },
            ],
            json_output=True,
        )
        return PlannerResult.model_validate_json(content)


def create_planner_provider(settings: Settings) -> PlannerProvider:
    if settings.planner_provider == "gemini":
        return GeminiPlannerProvider(
            base_url=settings.planner_base_url,
            api_key=settings.planner_api_key or settings.answer_api_key,
            model_name=settings.planner_model_name,
            timeout_seconds=settings.planner_timeout_seconds,
        )
    if settings.planner_provider == "openai_compatible":
        return OpenAICompatiblePlannerProvider(
            base_url=settings.planner_base_url,
            api_key=settings.planner_api_key,
            model_name=settings.planner_model_name,
            timeout_seconds=settings.planner_timeout_seconds,
        )
    raise ValueError(f"Unsupported planner provider: {settings.planner_provider}")


def _gemini_error_message(
    response: httpx.Response, *, component: str
) -> str:
    try:
        payload: Any = response.json()
        detail = str(payload.get("error", {}).get("message", response.text))
    except ValueError:
        detail = response.text
    return f"Gemini {component} request failed ({response.status_code}): {detail}"
