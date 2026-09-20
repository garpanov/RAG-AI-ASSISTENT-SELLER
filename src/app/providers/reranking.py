"""Switchable providers for second-stage RAG reranking."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

from app.core.config import Settings


class RerankerProvider(Protocol):
    async def rank(
        self, *, query: str, documents: list[str], limit: int
    ) -> list[int]: ...


class VectorOrderRerankerProvider:
    """Keep the cosine-distance order returned by pgvector."""

    async def rank(
        self, *, query: str, documents: list[str], limit: int
    ) -> list[int]:
        del query
        return list(range(min(limit, len(documents))))


class Qwen3RerankerProvider:
    """Lazy local Qwen3 cross-encoder, loaded only in the support worker."""

    def __init__(self, *, model_name: str) -> None:
        self._model_name = model_name
        self._model: CrossEncoder | None = None
        self._lock = asyncio.Lock()

    def _get_model(self) -> CrossEncoder:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    def _rank_sync(self, query: str, documents: list[str], limit: int) -> list[int]:
        rankings: Any = self._get_model().rank(
            query,
            documents,
            top_k=min(limit, len(documents)),
        )
        return [int(item["corpus_id"]) for item in rankings]

    async def rank(
        self, *, query: str, documents: list[str], limit: int
    ) -> list[int]:
        if not documents or limit <= 0:
            return []
        async with self._lock:
            return await asyncio.to_thread(
                self._rank_sync, query, documents, limit
            )


def create_reranker_provider(settings: Settings) -> RerankerProvider:
    if settings.reranker_provider == "vector":
        return VectorOrderRerankerProvider()
    if settings.reranker_provider == "qwen3":
        return Qwen3RerankerProvider(model_name=settings.reranker_model_name)
    raise ValueError(
        f"Unsupported reranker provider: {settings.reranker_provider}"
    )
