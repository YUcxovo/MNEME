"""Input-bound contracts for the platform operations repository."""

import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.repositories.operations import (
    MAX_DISPATCH_LEASE_SECONDS,
    MAX_FAILED_LIMIT,
    MAX_WINDOW_HOURS,
    PlatformOperationsRepository,
)

pytestmark = [pytest.mark.base, pytest.mark.db]


@pytest.mark.parametrize(
    ("now", "window_hours", "lease_seconds", "failed_limit", "message"),
    [
        (datetime(2026, 7, 30, 12), 24, 300, 20, "timezone-aware"),
        (datetime(2026, 7, 30, 12, tzinfo=UTC), 0, 300, 20, "Window hours"),
        (
            datetime(2026, 7, 30, 12, tzinfo=UTC),
            MAX_WINDOW_HOURS + 1,
            300,
            20,
            "Window hours",
        ),
        (datetime(2026, 7, 30, 12, tzinfo=UTC), 24, 0, 20, "Dispatch lease"),
        (
            datetime(2026, 7, 30, 12, tzinfo=UTC),
            24,
            MAX_DISPATCH_LEASE_SECONDS + 1,
            20,
            "Dispatch lease",
        ),
        (datetime(2026, 7, 30, 12, tzinfo=UTC), 24, 300, -1, "Failed limit"),
        (
            datetime(2026, 7, 30, 12, tzinfo=UTC),
            24,
            300,
            MAX_FAILED_LIMIT + 1,
            "Failed limit",
        ),
    ],
)
def test_snapshot_rejects_invalid_bounds_before_querying(
    now: datetime,
    window_hours: int,
    lease_seconds: int,
    failed_limit: int,
    message: str,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = PlatformOperationsRepository(cast(AsyncSession, session))

    with pytest.raises(ValueError, match=message):
        asyncio.run(
            repository.snapshot(
                now=now,
                window_hours=window_hours,
                dispatch_lease_seconds=lease_seconds,
                failed_limit=failed_limit,
            )
        )

    session.execute.assert_not_awaited()
