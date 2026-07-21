"""LLM orchestration: route -> cache -> budget -> provider -> telemetry."""

import time
from collections.abc import Mapping

import structlog
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.cache import LLMCache, build_cache_key
from mneme.ai.pricing import estimate_cost
from mneme.ai.providers import AnthropicProvider, DeepSeekProvider, LLMProvider, OpenAIProvider
from mneme.ai.routing import ModelRouter
from mneme.ai.types import (
    AITask,
    CompletionRequest,
    CompletionResult,
    ProviderName,
    ProviderNotConfiguredError,
)
from mneme.core.config import Settings

logger = structlog.get_logger(__name__)


class LLMService:
    """Single entry point for every LLM call made by the backend."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        providers: Mapping[ProviderName, LLMProvider],
        cache: LLMCache,
        budget: BudgetGuard,
    ) -> None:
        self._router = router
        self._providers = providers
        self._cache = cache
        self._budget = budget

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Serve a completion from cache or a provider, enforcing the budget."""
        route = self._router.resolve(request.task)
        cache_key = build_cache_key(route, request)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.info(
                "llm_completion_served",
                task=request.task.value,
                provider=route.provider.value,
                model=route.model,
                cached=True,
            )
            return cached

        provider = self._providers.get(route.provider)
        if provider is None:
            raise ProviderNotConfiguredError(
                f"Provider {route.provider.value!r} has no configured API key."
            )

        await self._budget.ensure_capacity()

        started = time.monotonic()
        response = await provider.complete(model=route.model, request=request)
        latency_ms = int((time.monotonic() - started) * 1000)

        cost = estimate_cost(response.model, response.usage)
        await self._budget.record_spend(cost)

        result = CompletionResult(
            text=response.text,
            task=request.task,
            provider=route.provider,
            model=response.model,
            prompt_version=request.prompt_version,
            usage=response.usage,
            estimated_cost=cost,
            latency_ms=latency_ms,
        )
        await self._cache.set(cache_key, result)

        logger.info(
            "llm_completion_served",
            task=request.task.value,
            provider=route.provider.value,
            model=response.model,
            cached=False,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            estimated_cost_usd=str(cost),
            latency_ms=latency_ms,
        )
        return result


def build_llm_service(settings: Settings, redis: Redis) -> LLMService:
    """Assemble the service from validated settings and the shared Redis client."""
    providers: dict[ProviderName, LLMProvider] = {}
    if settings.anthropic_api_key is not None:
        providers[ProviderName.ANTHROPIC] = AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if settings.deepseek_api_key is not None:
        providers[ProviderName.DEEPSEEK] = DeepSeekProvider(
            api_key=settings.deepseek_api_key.get_secret_value(),
            timeout_seconds=settings.llm_timeout_seconds,
            thinking_enabled=settings.deepseek_thinking_enabled,
        )
    if settings.openai_api_key is not None:
        providers[ProviderName.OPENAI] = OpenAIProvider(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return LLMService(
        router=ModelRouter(
            {
                AITask.SUMMARIZE: settings.llm_summary_model,
                AITask.QA: settings.llm_qa_model,
            }
        ),
        providers=providers,
        cache=LLMCache(
            redis,
            enabled=settings.ai_cache_enabled,
            ttl_seconds={
                AITask.SUMMARIZE: settings.ai_summary_cache_ttl_seconds,
                AITask.QA: settings.ai_qa_cache_ttl_seconds,
            },
        ),
        budget=BudgetGuard(redis, daily_cap_usd=settings.ai_daily_budget_usd),
    )
