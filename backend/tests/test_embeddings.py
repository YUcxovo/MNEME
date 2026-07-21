"""Embedding service: batching, budget enforcement, and provider contract."""

import asyncio
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetExceededError, BudgetGuard
from mneme.ai.embeddings import (
    PGVECTOR_DIMENSIONS,
    EmbeddingBatch,
    EmbeddingService,
    FakeEmbeddingProvider,
    FastEmbedEmbeddingProvider,
    build_embedding_service,
)
from mneme.ai.types import LLMProviderError
from mneme.core.config import EmbeddingBackend, Settings


def _guard(redis: FakeRedis, cap: str = "5") -> BudgetGuard:
    return BudgetGuard(cast(Redis, redis), daily_cap_usd=Decimal(cap))


@pytest.mark.base
@pytest.mark.rag
def test_texts_are_embedded_in_input_order_across_batches(fake_redis: FakeRedis) -> None:
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(
        provider=provider, budget=_guard(fake_redis), model="text-embedding-3-small", batch_size=2
    )
    texts = [f"chunk number {index}" for index in range(5)]

    vectors = asyncio.run(service.embed_texts(texts))

    assert len(vectors) == 5
    assert [len(call[1]) for call in provider.calls] == [2, 2, 1]
    single = asyncio.run(service.embed_texts([texts[3]]))
    assert single[0] == vectors[3]


@pytest.mark.base
@pytest.mark.rag
def test_embedding_spend_is_recorded_against_the_daily_budget(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)
    service = EmbeddingService(
        provider=FakeEmbeddingProvider(),
        budget=guard,
        model="text-embedding-3-small",
        batch_size=8,
    )

    asyncio.run(service.embed_texts(["some words to embed", "more words here"]))

    assert asyncio.run(guard.spent_today()) > 0


@pytest.mark.base
@pytest.mark.rag
def test_exhausted_budget_blocks_embedding_calls(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)
    asyncio.run(guard.record_spend(Decimal("5")))
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(
        provider=provider, budget=guard, model="text-embedding-3-small", batch_size=8
    )

    with pytest.raises(BudgetExceededError):
        asyncio.run(service.embed_texts(["blocked text"]))
    assert provider.calls == []


@pytest.mark.base
@pytest.mark.rag
def test_vector_count_mismatch_raises_provider_error(fake_redis: FakeRedis) -> None:
    class ShortProvider:
        async def embed(self, *, model: str, texts: list[str]) -> EmbeddingBatch:
            return EmbeddingBatch(vectors=((1.0, 0.0),), model=model, input_tokens=2)

    service = EmbeddingService(
        provider=ShortProvider(),
        budget=_guard(fake_redis),
        model="text-embedding-3-small",
        batch_size=8,
    )

    with pytest.raises(LLMProviderError):
        asyncio.run(service.embed_texts(["one", "two"]))


@pytest.mark.base
def test_fake_provider_is_deterministic_and_normalized() -> None:
    provider = FakeEmbeddingProvider(dimensions=8)

    first = asyncio.run(provider.embed(model="m", texts=["same text"]))
    second = asyncio.run(provider.embed(model="m", texts=["same text"]))

    assert first.vectors == second.vectors
    norm = sum(value * value for value in first.vectors[0])
    assert abs(norm - 1.0) < 1e-9


@pytest.mark.base
def test_embed_query_returns_one_vector(fake_redis: FakeRedis) -> None:
    service = EmbeddingService(
        provider=FakeEmbeddingProvider(),
        budget=_guard(fake_redis),
        model="text-embedding-3-small",
        batch_size=8,
    )

    vector = asyncio.run(service.embed_query("what is attention?"))

    assert len(vector) == 8


class _StubFastEmbed:
    def __init__(self, vectors: list[tuple[float, ...]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, documents: list[str]) -> list[tuple[float, ...]]:
        self.calls.append(list(documents))
        return self._vectors


@pytest.mark.base
@pytest.mark.rag
def test_fastembed_provider_normalizes_and_pads_to_schema_width() -> None:
    client = _StubFastEmbed([(3.0, 4.0), (0.0, 5.0)])
    provider = FastEmbedEmbeddingProvider(source_model="test-model", client=client)

    batch = asyncio.run(
        provider.embed(
            model="test-model+fastembed-pad1536-v1",
            texts=["first paper chunk", "second paper chunk"],
        )
    )

    assert client.calls == [["first paper chunk", "second paper chunk"]]
    assert len(batch.vectors) == 2
    assert len(batch.vectors[0]) == PGVECTOR_DIMENSIONS
    assert batch.vectors[0][:3] == pytest.approx((0.6, 0.8, 0.0))
    assert batch.vectors[1][:3] == pytest.approx((0.0, 1.0, 0.0))
    assert abs(sum(value * value for value in batch.vectors[0]) - 1.0) < 1e-9


@pytest.mark.base
@pytest.mark.rag
def test_fastembed_provider_rejects_vectors_wider_than_store() -> None:
    provider = FastEmbedEmbeddingProvider(
        source_model="test-model",
        dimensions=1,
        client=_StubFastEmbed([(1.0, 2.0)]),
    )

    with pytest.raises(LLMProviderError, match="2 dimensions"):
        asyncio.run(provider.embed(model="test-model", texts=["chunk"]))


@pytest.mark.base
@pytest.mark.rag
def test_fastembed_backend_builds_without_openai_key(fake_redis: FakeRedis) -> None:
    settings = Settings(
        ai_embedding_backend=EmbeddingBackend.FASTEMBED,
        ai_embedding_model="BAAI/bge-small-en-v1.5+fastembed-pad1536-v1",
        ai_local_embedding_model="BAAI/bge-small-en-v1.5",
        openai_api_key=None,
        _env_file=None,
    )

    service = build_embedding_service(settings, cast(Redis, fake_redis))

    assert service is not None
    assert service.model == "BAAI/bge-small-en-v1.5+fastembed-pad1536-v1"


@pytest.mark.base
def test_default_embedding_backend_still_requires_openai_key(fake_redis: FakeRedis) -> None:
    settings = Settings(openai_api_key=None, _env_file=None)

    assert build_embedding_service(settings, cast(Redis, fake_redis)) is None
