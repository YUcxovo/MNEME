"""Hard daily budget enforcement."""

import asyncio
from decimal import Decimal
from typing import cast

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetExceededError, BudgetGuard


def _guard(fake_redis: FakeRedis, cap: str = "5") -> BudgetGuard:
    return BudgetGuard(cast(Redis, fake_redis), daily_cap_usd=Decimal(cap))


@pytest.mark.base
def test_spend_accumulates_within_the_day(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)

    async def scenario() -> Decimal:
        await guard.record_spend(Decimal("1.25"))
        await guard.record_spend(Decimal("0.50"))
        return await guard.spent_today()

    assert asyncio.run(scenario()) == Decimal("1.75")


@pytest.mark.base
def test_capacity_check_passes_below_the_cap(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)

    async def scenario() -> None:
        await guard.record_spend(Decimal("4.99"))
        await guard.ensure_capacity()

    asyncio.run(scenario())


@pytest.mark.base
def test_capacity_check_fails_at_the_cap(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)

    async def scenario() -> None:
        await guard.record_spend(Decimal("5.00"))
        await guard.ensure_capacity()

    with pytest.raises(BudgetExceededError):
        asyncio.run(scenario())


@pytest.mark.base
def test_budget_keys_expire_after_two_days(fake_redis: FakeRedis) -> None:
    guard = _guard(fake_redis)

    asyncio.run(guard.record_spend(Decimal("1")))

    (key,) = fake_redis.ttls
    assert fake_redis.ttls[key] == 2 * 24 * 60 * 60
