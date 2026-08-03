"""Stable result and probe contracts for deployment preflight checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class CheckStatus(StrEnum):
    """Outcome of one deployment check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class PreflightCheck:
    """One stable, non-sensitive deployment check result."""

    id: str
    status: CheckStatus
    message: str
    details: dict[str, int | str] = field(default_factory=dict)

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
class PreflightReport:
    """Aggregate deployment readiness report."""

    checks: tuple[PreflightCheck, ...]
    generated_at: datetime

    @property
    def status(self) -> str:
        if any(item.status is CheckStatus.FAIL for item in self.checks):
            return "failed"
        if any(item.status is CheckStatus.WARN for item in self.checks):
            return "incomplete"
        return "ready"

    def as_dict(self) -> dict[str, object]:
        counts = {
            status.value: sum(item.status is status for item in self.checks)
            for status in CheckStatus
        }
        return {
            "checks": [item.as_dict() for item in self.checks],
            "counts": counts,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "schema_version": "deployment-preflight-v1",
            "status": self.status,
        }


class PreflightProbe(Protocol):
    """Live dependency surface used by the preflight runner."""

    async def ping_database(self) -> bool: ...

    async def database_revision(self) -> str | None: ...

    async def has_pgvector(self) -> bool: ...

    async def demo_user_exists(self, user_id: UUID) -> bool: ...

    async def connection_limits(self) -> tuple[int, int, int]: ...

    async def ping_redis(self) -> bool: ...

    async def paper_storage_writable(self) -> bool: ...

    async def backup_tools_available(self) -> bool: ...

    async def backup_credentials_configured(self) -> bool: ...

    async def aclose(self) -> None: ...


def boolean_check(check_id: str, passed: bool, success_message: str) -> PreflightCheck:
    """Build a consistent pass/fail result without unsafe observed values."""
    return PreflightCheck(
        id=check_id,
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        message=success_message if passed else f"{check_id.replace('_', ' ').capitalize()} failed.",
    )


def failed_check(check_id: str, message: str) -> PreflightCheck:
    """Build an explicit failed result with a bounded safe message."""
    return PreflightCheck(id=check_id, status=CheckStatus.FAIL, message=message)
