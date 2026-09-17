"""Switchable embedding providers."""

import asyncio
from typing import Any, Protocol, cast

from sentence_transformers import SentenceTransformer

from app.core.config import Settings


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class Qwen3EmbeddingProvider:
    """Local Qwen3 embedding adapter, loaded lazily in the worker process."""

    def __init__(
        self, *, model_name: str, dimensions: int, batch_size: int
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._model: SentenceTransformer | None = None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(
                self._model_name,
                trust_remote_code=True,
                truncate_dim=self._dimensions,
            )
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        encoded: Any = self._get_model().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return cast(list[list[float]], encoded.tolist())

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "qwen3":
        return Qwen3EmbeddingProvider(
            model_name=settings.embedding_model_name,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )
    raise ValueError(
        f"Unsupported embedding provider: {settings.embedding_provider}"
    )
