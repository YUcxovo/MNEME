"""Embedding service: batching, budget enforcement, and provider contract."""

import asyncio
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetExceededError, BudgetGuard
from mneme.ai.embeddings import EmbeddingBatch, EmbeddingService, FakeEmbeddingProvider
from mneme.ai.types import LLMProviderError


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
