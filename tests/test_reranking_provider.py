from types import SimpleNamespace
from typing import cast

import pytest

from app.core.config import Settings
from app.providers.reranking import (
    VectorOrderRerankerProvider,
    create_reranker_provider,
)


@pytest.mark.asyncio
async def test_vector_reranker_preserves_pgvector_order() -> None:
    provider = VectorOrderRerankerProvider()

    result = await provider.rank(
        query="delivery policy",
        documents=["first", "second", "third"],
        limit=2,
    )

    assert result == [0, 1]


def test_factory_creates_vector_reranker() -> None:
    settings = cast(
        Settings,
        SimpleNamespace(reranker_provider="vector"),
    )

    provider = create_reranker_provider(settings)

    assert isinstance(provider, VectorOrderRerankerProvider)
