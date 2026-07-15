"""LLM service orchestration: cache, budget, and provider wiring."""

import asyncio
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetExceededError, BudgetGuard
from mneme.ai.cache import LLMCache
from mneme.ai.providers import FakeLLMProvider, LLMProvider
from mneme.ai.routing import ModelRouter
from mneme.ai.service import LLMService
from mneme.ai.types import (
    AITask,
    ChatMessage,
    CompletionRequest,
    ProviderName,
    ProviderNotConfiguredError,
)

REQUEST = CompletionRequest(
    task=AITask.SUMMARIZE,
    messages=(ChatMessage(role="user", content="Summarize the abstract."),),
    prompt_version="v1",
)


def _service(
    fake_redis: FakeRedis,
    provider: FakeLLMProvider,
    *,
    daily_cap_usd: Decimal = Decimal("5"),
) -> LLMService:
    redis = cast(Redis, fake_redis)
    return LLMService(
        router=ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "gpt-4o"}),
        providers={ProviderName.ANTHROPIC: cast(LLMProvider, provider)},
        cache=LLMCache(
            redis, enabled=True, ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400}
        ),
        budget=BudgetGuard(redis, daily_cap_usd=daily_cap_usd),
    )


@pytest.mark.base
def test_completion_records_cost_and_telemetry_fields(fake_redis: FakeRedis) -> None:
    provider = FakeLLMProvider(default_response="A short generated summary.")
    service = _service(fake_redis, provider)

    result = asyncio.run(service.complete(REQUEST))

    assert result.text == "A short generated summary."
    assert result.provider is ProviderName.ANTHROPIC
    assert result.model == "claude-haiku-4-5"
    assert result.cached is False
    assert result.usage.output_tokens == 4
    assert result.estimated_cost > 0
    assert (
        asyncio.run(BudgetGuard(cast(Redis, fake_redis), daily_cap_usd=Decimal("5")).spent_today())
        > 0
    )


@pytest.mark.base
def test_second_identical_request_is_served_from_cache(fake_redis: FakeRedis) -> None:
    provider = FakeLLMProvider()
    service = _service(fake_redis, provider)

    async def scenario() -> tuple[bool, bool]:
        first = await service.complete(REQUEST)
        second = await service.complete(REQUEST)
        return first.cached, second.cached

    assert asyncio.run(scenario()) == (False, True)
    assert len(provider.calls) == 1


@pytest.mark.base
def test_exhausted_budget_blocks_the_provider_call(fake_redis: FakeRedis) -> None:
    provider = FakeLLMProvider()
    service = _service(fake_redis, provider, daily_cap_usd=Decimal("1"))

    async def scenario() -> None:
        await BudgetGuard(cast(Redis, fake_redis), daily_cap_usd=Decimal("1")).record_spend(
            Decimal("1")
        )
        await service.complete(REQUEST)

    with pytest.raises(BudgetExceededError):
        asyncio.run(scenario())
    assert provider.calls == []


@pytest.mark.base
def test_missing_provider_configuration_is_an_explicit_error(fake_redis: FakeRedis) -> None:
    provider = FakeLLMProvider()
    service = _service(fake_redis, provider)
    qa_request = REQUEST.model_copy(update={"task": AITask.QA})

    with pytest.raises(ProviderNotConfiguredError):
        asyncio.run(service.complete(qa_request))
