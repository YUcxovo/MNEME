"""Contracts and configuration for private platform health checks."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit


class PlatformHealthConfigurationError(ValueError):
    """A platform health threshold or local target is unsafe."""


class HealthCheckStatus(StrEnum):
    """Outcome of one private platform check."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class HealthCheck:
    """One aggregate-only platform check result."""

    id: str
    status: HealthCheckStatus
    message: str
    details: dict[str, int | float | str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "message": self.message,
            "status": self.status.value,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class PlatformHealthReport:
    """Stable machine-readable host and service health report."""

    checks: tuple[HealthCheck, ...]
    generated_at: datetime

    @property
    def status(self) -> str:
        return (
            "unhealthy"
            if any(check.status is HealthCheckStatus.FAIL for check in self.checks)
            else "healthy"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "checks": [check.as_dict() for check in self.checks],
            "counts": {
                status.value: sum(check.status is status for check in self.checks)
                for status in HealthCheckStatus
            },
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "schema_version": "platform-health-v1",
            "status": self.status,
        }


@dataclass(frozen=True)
class PlatformHealthConfig:
    """Bounded thresholds for one production host."""

    base_url: str = "http://127.0.0.1:8000"
    backup_dir: Path = Path("/var/backups/mneme")
    minimum_disk_available_percent: int = 10
    minimum_memory_available_percent: int = 10
    maximum_backup_age_hours: int = 30
    maximum_ingestion_age_hours: int = 36
    maximum_digest_age_hours: int = 192
    maximum_failed_jobs: int = 0
    operations_window_hours: int = 24
    dispatch_lease_seconds: int = 300
    probe_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        _validate_loopback_url(self.base_url)
        if not self.backup_dir.is_absolute() or ".." in self.backup_dir.parts:
            raise PlatformHealthConfigurationError("Backup directory must be absolute")
        for value, label in (
            (self.minimum_disk_available_percent, "disk threshold"),
            (self.minimum_memory_available_percent, "memory threshold"),
        ):
            if not 1 <= value <= 99:
                raise PlatformHealthConfigurationError(f"Invalid {label}")
        for value, label in (
            (self.maximum_backup_age_hours, "backup age"),
            (self.maximum_ingestion_age_hours, "ingestion age"),
            (self.maximum_digest_age_hours, "digest age"),
        ):
            if not 1 <= value <= 720:
                raise PlatformHealthConfigurationError(f"Invalid {label}")
        if not 0 <= self.maximum_failed_jobs <= 100:
            raise PlatformHealthConfigurationError("Invalid failed-job threshold")
        if not 1 <= self.operations_window_hours <= 720:
            raise PlatformHealthConfigurationError("Invalid operations window")
        if not 1 <= self.dispatch_lease_seconds <= 86400:
            raise PlatformHealthConfigurationError("Invalid dispatch lease")
        if not 0.1 <= self.probe_timeout_seconds <= 30:
            raise PlatformHealthConfigurationError("Invalid probe timeout")


class PlatformHealthProbe(Protocol):
    """Host-private dependencies used by the health runner."""

    async def api_liveness(self) -> bool: ...

    async def api_readiness(self) -> bool: ...

    async def worker_alive(self) -> bool: ...

    async def operations_snapshot(self, now: datetime) -> dict[str, object]: ...

    async def paper_disk_space(self) -> tuple[int, int]: ...

    async def backup_disk_space(self) -> tuple[int, int]: ...

    async def memory_space(self) -> tuple[int, int]: ...

    async def latest_backup(self) -> datetime: ...

    async def pipeline_successes(self) -> dict[str, datetime | None]: ...

    async def aclose(self) -> None: ...


def _validate_loopback_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname is None
    ):
        raise PlatformHealthConfigurationError("Health URL must be a plain loopback HTTP origin")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if not loopback:
        raise PlatformHealthConfigurationError("Health URL must resolve to loopback")
