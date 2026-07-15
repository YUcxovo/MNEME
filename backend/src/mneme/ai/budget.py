"""Hard daily spending cap shared across API workers via Redis."""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from redis.asyncio import Redis

from mneme.ai.types import AIError

logger = structlog.get_logger(__name__)

_KEY_TTL_SECONDS = 2 * 24 * 60 * 60


class BudgetExceededError(AIError):
    """The daily LLM budget is exhausted; no further provider calls today."""

    def __init__(self, *, spent_usd: Decimal, cap_usd: Decimal) -> None:
        super().__init__(
            f"Daily LLM budget exhausted: spent {spent_usd:.4f} USD of {cap_usd:.4f} USD."
        )
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd


class BudgetGuard:
    """Track LLM spend in Redis and refuse calls once the daily cap is hit.

    The check-then-spend sequence is not atomic, so concurrent calls may
    overshoot the cap by at most one in-flight completion each — acceptable
    for a hard *daily* stop, and it never blocks recording actual spend.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        daily_cap_usd: Decimal,
        key_prefix: str = "mneme:ai:budget",
    ) -> None:
        self._redis = redis
        self._daily_cap_usd = daily_cap_usd
        self._key_prefix = key_prefix

    def _key(self) -> str:
        return f"{self._key_prefix}:{datetime.now(UTC).date().isoformat()}"

    async def spent_today(self) -> Decimal:
        """Return the spend recorded for the current UTC day."""
        raw = await self._redis.get(self._key())
        return Decimal(raw) if raw is not None else Decimal(0)

    async def ensure_capacity(self) -> None:
        """Raise :class:`BudgetExceededError` when the daily cap is reached."""
        spent = await self.spent_today()
        if spent >= self._daily_cap_usd:
            logger.warning(
                "llm_budget_exhausted",
                spent_usd=str(spent),
                cap_usd=str(self._daily_cap_usd),
            )
            raise BudgetExceededError(spent_usd=spent, cap_usd=self._daily_cap_usd)

    async def record_spend(self, cost_usd: Decimal) -> None:
        """Add one completion's cost to today's counter."""
        key = self._key()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(key, float(cost_usd))
            pipe.expire(key, _KEY_TTL_SECONDS, nx=True)
            await pipe.execute()
