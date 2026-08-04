"""Tests for aggregate-only private platform health checks."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mneme.core.config import Settings
from mneme.ops.health import run_platform_health
from mneme.ops.health_types import (
    HealthCheckStatus,
    PlatformHealthConfig,
    PlatformHealthConfigurationError,
)

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(_env_file=None)


class FakeHealthProbe:
    def __init__(self, **overrides: object) -> None:
        self.values: dict[str, object] = {
            "api_liveness": True,
            "api_readiness": True,
            "worker_alive": True,
            "operations_snapshot": {
                "jobs": {
                    "failed": 0,
                    "stale_dispatched_queued": 0,
                    "stale_running": 0,
                    "undispatched_queued": 0,
                }
            },
            "paper_disk_space": (1000, 500),
            "backup_disk_space": (1000, 400),
            "memory_space": (1000, 300),
            "latest_backup": NOW - timedelta(hours=2),
            "pipeline_successes": {
                "fetch_metadata": NOW - timedelta(hours=3),
                "assemble_digest": NOW - timedelta(hours=24),
            },
            "aclose": True,
        }
        self.values.update(overrides)
        self.closed = False

    async def _get(self, key: str) -> object:
        value = self.values[key]
        if isinstance(value, Exception):
            raise value
        return value

    async def api_liveness(self) -> bool:
        return bool(await self._get("api_liveness"))

    async def api_readiness(self) -> bool:
        return bool(await self._get("api_readiness"))

    async def worker_alive(self) -> bool:
        return bool(await self._get("worker_alive"))

    async def operations_snapshot(self, now: datetime) -> dict[str, object]:
        assert now == NOW
        value = await self._get("operations_snapshot")
        assert isinstance(value, dict)
        return value

    async def paper_disk_space(self) -> tuple[int, int]:
        value = await self._get("paper_disk_space")
        assert isinstance(value, tuple)
        return value

    async def backup_disk_space(self) -> tuple[int, int]:
        value = await self._get("backup_disk_space")
        assert isinstance(value, tuple)
        return value

    async def memory_space(self) -> tuple[int, int]:
        value = await self._get("memory_space")
        assert isinstance(value, tuple)
        return value

    async def latest_backup(self) -> datetime:
        value = await self._get("latest_backup")
        assert isinstance(value, datetime)
        return value

    async def pipeline_successes(self) -> dict[str, datetime | None]:
        value = await self._get("pipeline_successes")
        assert isinstance(value, dict)
        return value

    async def aclose(self) -> None:
        self.closed = True
        await self._get("aclose")


@pytest.mark.base
def test_platform_health_reports_all_healthy_aggregates(tmp_path: Path) -> None:
    probe = FakeHealthProbe()
    config = PlatformHealthConfig(backup_dir=tmp_path)

    report = asyncio.run(run_platform_health(_settings(), config, probe=probe, now=NOW))

    assert report.status == "healthy"
    assert probe.closed
    assert [check.id for check in report.checks] == [
        "api_liveness",
        "api_readiness",
        "arq_worker",
        "pipeline_operations",
        "paper_disk",
        "backup_disk",
        "memory",
        "backup_freshness",
        "ingestion_freshness",
        "digest_freshness",
    ]
    assert all(check.status is HealthCheckStatus.PASS for check in report.checks)
    payload = report.as_dict()
    assert payload["counts"] == {"fail": 0, "pass": 10}
    assert payload["generated_at"] == "2026-08-03T12:00:00Z"
    assert "job_id" not in json.dumps(payload)
    assert "idempotency_key" not in json.dumps(payload)


@pytest.mark.base
@pytest.mark.parametrize(
    ("overrides", "failed_check"),
    [
        ({"api_liveness": False}, "api_liveness"),
        ({"api_readiness": False}, "api_readiness"),
        ({"worker_alive": False}, "arq_worker"),
        (
            {
                "operations_snapshot": {
                    "jobs": {
                        "failed": 1,
                        "stale_dispatched_queued": 0,
                        "stale_running": 0,
                        "undispatched_queued": 0,
                    }
                }
            },
            "pipeline_operations",
        ),
        (
            {
                "operations_snapshot": {
                    "jobs": {
                        "failed": 0,
                        "stale_dispatched_queued": 0,
                        "stale_running": 1,
                        "undispatched_queued": 0,
                    }
                }
            },
            "pipeline_operations",
        ),
        ({"operations_snapshot": RuntimeError("job secret")}, "pipeline_operations"),
        ({"paper_disk_space": (100, 9)}, "paper_disk"),
        ({"backup_disk_space": (100, 9)}, "backup_disk"),
        ({"memory_space": (100, 9)}, "memory"),
        ({"latest_backup": NOW - timedelta(hours=31)}, "backup_freshness"),
        ({"latest_backup": NOW + timedelta(hours=1)}, "backup_freshness"),
        (
            {"pipeline_successes": {"fetch_metadata": None, "assemble_digest": NOW}},
            "ingestion_freshness",
        ),
        (
            {
                "pipeline_successes": {
                    "fetch_metadata": NOW,
                    "assemble_digest": NOW - timedelta(hours=193),
                }
            },
            "digest_freshness",
        ),
        ({"pipeline_successes": ConnectionError("postgresql://secret")}, "ingestion_freshness"),
        ({"aclose": RuntimeError("redis://secret")}, "probe_cleanup"),
    ],
)
def test_platform_health_contains_independent_failures(
    tmp_path: Path, overrides: dict[str, object], failed_check: str
) -> None:
    report = asyncio.run(
        run_platform_health(
            _settings(),
            PlatformHealthConfig(backup_dir=tmp_path),
            probe=FakeHealthProbe(**overrides),
            now=NOW,
        )
    )
    checks = {check.id: check for check in report.checks}
    serialized = json.dumps(report.as_dict())

    assert report.status == "unhealthy"
    assert checks[failed_check].status is HealthCheckStatus.FAIL
    assert "secret" not in serialized
    assert "job_id" not in serialized


@pytest.mark.base
@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "https://api.example.com"},
        {"base_url": "http://user:secret@127.0.0.1:8000"},
        {"backup_dir": Path("relative")},
        {"minimum_disk_available_percent": 0},
        {"minimum_memory_available_percent": 100},
        {"maximum_backup_age_hours": 721},
        {"maximum_failed_jobs": 101},
        {"probe_timeout_seconds": 0},
    ],
)
def test_platform_health_config_rejects_unsafe_values(overrides: dict[str, object]) -> None:
    with pytest.raises(PlatformHealthConfigurationError):
        PlatformHealthConfig(**overrides)  # type: ignore[arg-type]


@pytest.mark.base
def test_platform_health_requires_timezone_aware_observation(tmp_path: Path) -> None:
    with pytest.raises(PlatformHealthConfigurationError):
        asyncio.run(
            run_platform_health(
                _settings(),
                PlatformHealthConfig(backup_dir=tmp_path),
                probe=FakeHealthProbe(),
                now=datetime(2026, 8, 3),
            )
        )
