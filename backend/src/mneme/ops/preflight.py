"""Production deployment preflight orchestration with non-sensitive output."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

from mneme.core.config import Settings
from mneme.ops.preflight_probe import ProductionPreflightProbe
from mneme.ops.preflight_static import static_preflight_checks
from mneme.ops.preflight_types import (
    CheckStatus,
    PreflightCheck,
    PreflightProbe,
    PreflightReport,
    boolean_check,
    failed_check,
)

_T = TypeVar("_T")


async def run_preflight(
    settings: Settings,
    *,
    expected_head: str,
    offline: bool = False,
    probe: PreflightProbe | None = None,
    now: datetime | None = None,
) -> PreflightReport:
    """Run static and optional live checks, closing dependency clients in all cases."""
    checks = list(static_preflight_checks(settings))
    if offline:
        checks.append(
            PreflightCheck(
                id="live_dependencies",
                status=CheckStatus.WARN,
                message="Live dependency checks were explicitly skipped.",
            )
        )
        return PreflightReport(tuple(checks), now or datetime.now(UTC))

    resolved_probe = probe or ProductionPreflightProbe(settings)
    timeout = settings.readiness_timeout_seconds
    try:
        checks.append(
            await _safe_live_boolean(
                "postgresql", resolved_probe.ping_database, timeout, "PostgreSQL is reachable."
            )
        )
        checks.append(
            await _safe_live_value(
                "migration_head",
                resolved_probe.database_revision,
                timeout,
                lambda value: value == expected_head,
                "The database migration is at the checkout head.",
            )
        )
        checks.append(
            await _safe_live_boolean(
                "pgvector_extension",
                resolved_probe.has_pgvector,
                timeout,
                "The pgvector extension is installed.",
            )
        )
        if settings.demo_user_id is None:
            checks.append(failed_check("demo_user", "The configured demo user is unavailable."))
        else:
            checks.append(
                await _safe_live_boolean(
                    "demo_user",
                    lambda: resolved_probe.demo_user_exists(settings.demo_user_id),
                    timeout,
                    "The configured demo user exists.",
                )
            )
        checks.append(await _connection_capacity_check(settings, resolved_probe, timeout))
        checks.append(
            await _safe_live_boolean(
                "redis", resolved_probe.ping_redis, timeout, "Redis is reachable."
            )
        )
        checks.append(
            await _safe_live_boolean(
                "paper_storage",
                resolved_probe.paper_storage_writable,
                timeout,
                "The paper storage directory is writable.",
            )
        )
        checks.append(
            await _safe_live_boolean(
                "backup_tools",
                resolved_probe.backup_tools_available,
                timeout,
                "PostgreSQL backup clients are installed.",
            )
        )
        checks.append(
            await _safe_live_boolean(
                "backup_credentials",
                resolved_probe.backup_credentials_configured,
                timeout,
                "Private libpq backup credentials are configured.",
            )
        )
    finally:
        try:
            await resolved_probe.aclose()
        except Exception:
            checks.append(
                failed_check("probe_cleanup", "Dependency clients did not close cleanly.")
            )
    return PreflightReport(tuple(checks), now or datetime.now(UTC))


async def _connection_capacity_check(
    settings: Settings, probe: PreflightProbe, timeout: float
) -> PreflightCheck:
    try:
        async with asyncio.timeout(timeout):
            maximum, reserved = await probe.connection_limits()
        available = maximum - reserved
        headroom = max(10, available // 5)
        required = (settings.api_workers + 2) * (
            settings.database_pool_size + settings.database_max_overflow
        )
        passed = required <= available - headroom
        return PreflightCheck(
            id="database_capacity",
            status=CheckStatus.PASS if passed else CheckStatus.FAIL,
            message=(
                "Database connection capacity includes operational headroom."
                if passed
                else "Database connection capacity is insufficient."
            ),
            details={"available": available, "headroom": headroom, "required": required},
        )
    except Exception:
        return failed_check("database_capacity", "Database capacity could not be verified.")


async def _safe_live_boolean(
    check_id: str,
    action: Callable[[], Awaitable[bool]],
    timeout: float,
    success_message: str,
) -> PreflightCheck:
    return await _safe_live_value(check_id, action, timeout, bool, success_message)


async def _safe_live_value(
    check_id: str,
    action: Callable[[], Awaitable[_T]],
    timeout: float,
    predicate: Callable[[_T], bool],
    success_message: str,
) -> PreflightCheck:
    try:
        async with asyncio.timeout(timeout):
            passed = predicate(await action())
    except Exception:
        passed = False
    return boolean_check(check_id, passed, success_message)
