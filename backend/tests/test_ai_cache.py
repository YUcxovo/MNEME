"""Cache keys, TTL policy, and invalidation."""

import asyncio
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.cache import LLMCache, build_cache_key
from mneme.ai.routing import ModelRoute
from mneme.ai.types import (
    AITask,
    ChatMessage,
    CompletionRequest,
    CompletionResult,
    ProviderName,
    TokenUsage,
)

ROUTE = ModelRoute(provider=ProviderName.ANTHROPIC, model="claude-haiku-4-5")


def _request(
    content: str = "Summarize this paper.", prompt_version: str = "v1"
) -> CompletionRequest:
    return CompletionRequest(
        task=AITask.SUMMARIZE,
        messages=(ChatMessage(role="user", content=content),),
        prompt_version=prompt_version,
    )


def _result(task: AITask = AITask.SUMMARIZE) -> CompletionResult:
    return CompletionResult(
        text="A summary.",
        task=task,
        provider=ProviderName.ANTHROPIC,
        model="claude-haiku-4-5",
        prompt_version="v1",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        estimated_cost=Decimal("0.0001"),
        latency_ms=42,
    )


def _cache(fake_redis: FakeRedis, *, enabled: bool = True) -> LLMCache:
    return LLMCache(
        cast(Redis, fake_redis),
        enabled=enabled,
        ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400},
    )


@pytest.mark.base
def test_cache_key_is_deterministic_and_input_sensitive() -> None:
    key = build_cache_key(ROUTE, _request())

    assert key == build_cache_key(ROUTE, _request())
    assert key.startswith("mneme:ai:cache:summarize:v1:")
    assert key != build_cache_key(ROUTE, _request(content="Different question."))
    assert key != build_cache_key(ROUTE, _request(prompt_version="v2"))


@pytest.mark.base
def test_roundtrip_marks_results_as_cached(fake_redis: FakeRedis) -> None:
    cache = _cache(fake_redis)
    key = build_cache_key(ROUTE, _request())

    async def scenario() -> CompletionResult | None:
        await cache.set(key, _result())
        return await cache.get(key)

    hit = asyncio.run(scenario())

    assert hit is not None
    assert hit.cached is True
    assert hit.text == "A summary."
    assert fake_redis.ttls[key] == 604800


@pytest.mark.base
def test_disabled_cache_never_reads_or_writes(fake_redis: FakeRedis) -> None:
    cache = _cache(fake_redis, enabled=False)
    key = build_cache_key(ROUTE, _request())

    async def scenario() -> CompletionResult | None:
        await cache.set(key, _result())
        return await cache.get(key)

    assert asyncio.run(scenario()) is None
    assert fake_redis.store == {}


@pytest.mark.base
def test_corrupt_entries_are_dropped(fake_redis: FakeRedis) -> None:
    cache = _cache(fake_redis)
    key = build_cache_key(ROUTE, _request())
    fake_redis.store[key] = "not-json"

    assert asyncio.run(cache.get(key)) is None
    assert key not in fake_redis.store


@pytest.mark.base
def test_invalidation_is_scoped_to_task_and_prompt_version(fake_redis: FakeRedis) -> None:
    cache = _cache(fake_redis)
    summarize_v1 = build_cache_key(ROUTE, _request())
    summarize_v2 = build_cache_key(ROUTE, _request(prompt_version="v2"))

    async def scenario() -> int:
        await cache.set(summarize_v1, _result())
        await cache.set(summarize_v2, _result())
        return await cache.invalidate(task=AITask.SUMMARIZE, prompt_version="v1")

    assert asyncio.run(scenario()) == 1
    assert summarize_v1 not in fake_redis.store
    assert summarize_v2 in fake_redis.store
