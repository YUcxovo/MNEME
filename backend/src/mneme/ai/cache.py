"""Completion cache: deterministic keys, per-task TTLs, prompt-version scoped."""

import hashlib
import json

import structlog
from redis.asyncio import Redis

from mneme.ai.routing import ModelRoute
from mneme.ai.types import AITask, CompletionRequest, CompletionResult

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "mneme:ai:cache"


def build_cache_key(route: ModelRoute, request: CompletionRequest) -> str:
    """Return the deterministic cache key for one completion request.

    The key embeds task and prompt version as plain segments so whole prompt
    generations can be invalidated by pattern, and hashes the full request
    body so any input change misses cleanly.
    """
    canonical = json.dumps(
        {
            "task": request.task.value,
            "provider": route.provider.value,
            "model": route.model,
            "prompt_version": request.prompt_version,
            "system": request.system,
            "messages": [[message.role, message.content] for message in request.messages],
            "max_output_tokens": request.max_output_tokens,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}:{request.task.value}:{request.prompt_version}:{digest}"


class LLMCache:
    """Cache completed generations in Redis with task-specific TTLs."""

    def __init__(
        self,
        redis: Redis,
        *,
        enabled: bool,
        ttl_seconds: dict[AITask, int],
    ) -> None:
        self._redis = redis
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds

    async def get(self, key: str) -> CompletionResult | None:
        """Return the cached result for a key, marked as a cache hit."""
        if not self._enabled:
            return None
        payload = await self._redis.get(key)
        if payload is None:
            return None
        try:
            result = CompletionResult.model_validate_json(payload)
        except ValueError:
            logger.warning("llm_cache_corrupt_entry", key=key)
            await self._redis.delete(key)
            return None
        return result.model_copy(update={"cached": True})

    async def set(self, key: str, result: CompletionResult) -> None:
        """Store a completed generation under its per-task TTL."""
        if not self._enabled:
            return
        ttl = self._ttl_seconds[result.task]
        await self._redis.set(key, result.model_dump_json(), ex=ttl)

    async def invalidate(self, *, task: AITask, prompt_version: str | None = None) -> int:
        """Delete cached generations for a task, optionally one prompt version.

        Uses SCAN over a key pattern; acceptable at demo scale, revisit if the
        keyspace grows past a few hundred thousand entries.
        """
        version_segment = prompt_version if prompt_version is not None else "*"
        pattern = f"{_KEY_PREFIX}:{task.value}:{version_segment}:*"
        deleted = 0
        async for key in self._redis.scan_iter(match=pattern):
            deleted += await self._redis.delete(key)
        logger.info(
            "llm_cache_invalidated",
            task=task.value,
            prompt_version=prompt_version,
            deleted=deleted,
        )
        return deleted
