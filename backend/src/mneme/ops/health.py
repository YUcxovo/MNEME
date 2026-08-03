"""Aggregate private platform health without exposing infrastructure details."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar, cast

from mneme.core.config import Settings
from mneme.ops.health_probe import ProductionHealthProbe
from mneme.ops.health_types import (
    HealthCheck,
    HealthCheckStatus,
    PlatformHealthConfig,
    PlatformHealthConfigurationError,
    PlatformHealthProbe,
    PlatformHealthReport,
)

_T = TypeVar("_T")


async def run_platform_health(
    settings: Settings,
    config: PlatformHealthConfig,
    *,
    probe: PlatformHealthProbe | None = None,
    now: datetime | None = None,
) -> PlatformHealthReport:
    """Run every independent host check and close dependency clients."""
    requested_time = now or datetime.now(UTC)
    if requested_time.tzinfo is None or requested_time.utcoffset() is None:
        raise PlatformHealthConfigurationError("Health observation time must include a timezone")
    observed_at = requested_time.astimezone(UTC)
    resolved_probe = probe or ProductionHealthProbe(settings, config)
    timeout = config.probe_timeout_seconds
    checks: list[HealthCheck] = []
    try:
        checks.append(
            await _safe_boolean(
                "api_liveness", resolved_probe.api_liveness, timeout, "The API process is live."
            )
        )
        checks.append(
            await _safe_boolean(
                "api_readiness",
                resolved_probe.api_readiness,
                timeout,
                "The API dependencies are ready.",
            )
        )
        checks.append(
            await _safe_boolean(
                "arq_worker", resolved_probe.worker_alive, timeout, "The ARQ worker is reporting."
            )
        )
        checks.append(await _operations_check(resolved_probe, config, observed_at, timeout))
        checks.append(
            await _space_check(
                "paper_disk",
                resolved_probe.paper_disk_space,
                config.minimum_disk_available_percent,
                timeout,
            )
        )
        checks.append(
            await _space_check(
                "backup_disk",
                resolved_probe.backup_disk_space,
                config.minimum_disk_available_percent,
                timeout,
            )
        )
        checks.append(
            await _space_check(
                "memory",
                resolved_probe.memory_space,
                config.minimum_memory_available_percent,
                timeout,
            )
        )
        checks.append(
            await _freshness_check(
                "backup_freshness",
                resolved_probe.latest_backup,
                config.maximum_backup_age_hours,
                observed_at,
                timeout,
            )
        )
        checks.extend(await _pipeline_checks(resolved_probe, config, observed_at, timeout))
    finally:
        try:
            await resolved_probe.aclose()
        except Exception:
            checks.append(_failed("probe_cleanup", "Health clients did not close cleanly."))
    return PlatformHealthReport(tuple(checks), observed_at)


async def _operations_check(
    probe: PlatformHealthProbe,
    config: PlatformHealthConfig,
    now: datetime,
    timeout: float,
) -> HealthCheck:
    try:
        async with asyncio.timeout(timeout):
            snapshot = await probe.operations_snapshot(now)
        jobs = cast(dict[str, object], snapshot["jobs"])
        failed = int(cast(int, jobs["failed"]))
        undispatched = int(cast(int, jobs["undispatched_queued"]))
        stale = int(cast(int, jobs["stale_dispatched_queued"]))
        passed = failed <= config.maximum_failed_jobs and undispatched == 0 and stale == 0
        return HealthCheck(
            id="pipeline_operations",
            status=HealthCheckStatus.PASS if passed else HealthCheckStatus.FAIL,
            message=(
                "Recent pipeline operations are within thresholds."
                if passed
                else "Recent pipeline operations exceed thresholds."
            ),
            details={"failed": failed, "stale": stale, "undispatched": undispatched},
        )
    except Exception:
        return _failed("pipeline_operations", "Pipeline operations could not be verified.")


async def _space_check(
    check_id: str,
    action: Callable[[], Awaitable[tuple[int, int]]],
    minimum_percent: int,
    timeout: float,
) -> HealthCheck:
    try:
        async with asyncio.timeout(timeout):
            total, available = await action()
        if total <= 0 or available < 0:
            raise ValueError("Invalid host capacity")
        available_percent = int(available * 100 / total)
        passed = available_percent >= minimum_percent
        return HealthCheck(
            id=check_id,
            status=HealthCheckStatus.PASS if passed else HealthCheckStatus.FAIL,
            message=(
                f"{check_id.replace('_', ' ').capitalize()} is within threshold."
                if passed
                else f"{check_id.replace('_', ' ').capitalize()} is below threshold."
            ),
            details={"available_percent": available_percent},
        )
    except Exception:
        return _failed(check_id, f"{check_id.replace('_', ' ').capitalize()} is unavailable.")


async def _freshness_check(
    check_id: str,
    action: Callable[[], Awaitable[datetime]],
    maximum_age_hours: int,
    now: datetime,
    timeout: float,
) -> HealthCheck:
    try:
        async with asyncio.timeout(timeout):
            timestamp = (await action()).astimezone(UTC)
        age_hours = (now - timestamp).total_seconds() / 3600
        passed = 0 <= age_hours <= maximum_age_hours
        return HealthCheck(
            id=check_id,
            status=HealthCheckStatus.PASS if passed else HealthCheckStatus.FAIL,
            message=(
                f"{check_id.replace('_', ' ').capitalize()} is within threshold."
                if passed
                else f"{check_id.replace('_', ' ').capitalize()} exceeds threshold."
            ),
            details={"age_hours": round(age_hours, 2)},
        )
    except Exception:
        return _failed(check_id, f"{check_id.replace('_', ' ').capitalize()} is unavailable.")


async def _pipeline_checks(
    probe: PlatformHealthProbe,
    config: PlatformHealthConfig,
    now: datetime,
    timeout: float,
) -> tuple[HealthCheck, HealthCheck]:
    try:
        async with asyncio.timeout(timeout):
            successes = await probe.pipeline_successes()
    except Exception:
        return (
            _failed("ingestion_freshness", "Ingestion freshness is unavailable."),
            _failed("digest_freshness", "Digest freshness is unavailable."),
        )

    async def value(timestamp: datetime | None) -> datetime:
        if timestamp is None:
            raise ValueError("No successful pipeline job")
        return timestamp

    return (
        await _freshness_check(
            "ingestion_freshness",
            lambda: value(successes.get("fetch_metadata")),
            config.maximum_ingestion_age_hours,
            now,
            timeout,
        ),
        await _freshness_check(
            "digest_freshness",
            lambda: value(successes.get("assemble_digest")),
            config.maximum_digest_age_hours,
            now,
            timeout,
        ),
    )


async def _safe_boolean(
    check_id: str,
    action: Callable[[], Awaitable[bool]],
    timeout: float,
    success_message: str,
) -> HealthCheck:
    try:
        async with asyncio.timeout(timeout):
            passed = bool(await action())
    except Exception:
        passed = False
    return HealthCheck(
        id=check_id,
        status=HealthCheckStatus.PASS if passed else HealthCheckStatus.FAIL,
        message=success_message if passed else f"{check_id.replace('_', ' ').capitalize()} failed.",
    )


def _failed(check_id: str, message: str) -> HealthCheck:
    return HealthCheck(id=check_id, status=HealthCheckStatus.FAIL, message=message)
