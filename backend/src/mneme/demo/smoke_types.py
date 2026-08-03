"""Safe configuration and result types for the public MVP smoke test."""

from __future__ import annotations

import ipaddress
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from mneme.api.routes.onboarding_support import normalize_arxiv_reference


class MvpSmokeConfigurationError(ValueError):
    """A smoke-test input is missing, malformed, or unsafe."""


class MvpSmokeError(RuntimeError):
    """One smoke-test check failed without retaining response content."""

    def __init__(
        self,
        check: str,
        code: str,
        *,
        operation: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(f"MVP smoke check {check} failed")
        self.check = check
        self.code = code
        self.operation = operation
        self.status_code = status_code

    def safe_details(self) -> dict[str, str | int | bool]:
        """Return only bounded diagnostic fields suitable for shared logs."""
        details: dict[str, str | int | bool] = {"code": self.code}
        if self.operation is not None:
            details["operation"] = self.operation
        if self.status_code is not None:
            details["status_code"] = self.status_code
        return details


@dataclass(frozen=True)
class MvpSmokeConfig:
    """Bounded inputs for an HTTP-only deployment acceptance run."""

    base_url: str
    seed_arxiv_id: str = "1706.03762"
    question: str | None = None
    request_timeout_seconds: float = 30
    deadline_seconds: float = 600
    poll_interval_seconds: float = 1
    maximum_summary_jobs: int = 8
    maximum_catalog_pages: int = 5
    minimum_graph_nodes: int = 2
    minimum_graph_edges: int = 1

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url)
        try:
            normalized_seed = normalize_arxiv_reference(self.seed_arxiv_id)
        except ValueError as exception:
            raise MvpSmokeConfigurationError("Seed arXiv ID is invalid") from exception
        object.__setattr__(self, "seed_arxiv_id", normalized_seed)
        if self.question is not None and not 1 <= len(self.question.strip()) <= 500:
            raise MvpSmokeConfigurationError("Question length is invalid")
        if not 1 <= self.request_timeout_seconds <= 120:
            raise MvpSmokeConfigurationError("Request timeout is invalid")
        if not 10 <= self.deadline_seconds <= 1800:
            raise MvpSmokeConfigurationError("Smoke deadline is invalid")
        if not 0.1 <= self.poll_interval_seconds <= 30:
            raise MvpSmokeConfigurationError("Poll interval is invalid")
        if not 1 <= self.maximum_summary_jobs <= 20:
            raise MvpSmokeConfigurationError("Summary job limit is invalid")
        if not 1 <= self.maximum_catalog_pages <= 20:
            raise MvpSmokeConfigurationError("Catalog page limit is invalid")
        if not 1 <= self.minimum_graph_nodes <= 200:
            raise MvpSmokeConfigurationError("Minimum graph nodes is invalid")
        if not 0 <= self.minimum_graph_edges <= 1000:
            raise MvpSmokeConfigurationError("Minimum graph edges is invalid")


@dataclass(frozen=True)
class SmokeCheck:
    """One sanitized acceptance check."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    details: dict[str, str | int | bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {"details": self.details, "name": self.name, "status": self.status}


@dataclass(frozen=True)
class MvpSmokeReport:
    """Stable machine-readable result of the public API smoke sequence."""

    seed_arxiv_id: str
    checks: tuple[SmokeCheck, ...]

    @property
    def status(self) -> Literal["passed", "failed"]:
        return "failed" if any(check.status == "failed" for check in self.checks) else "passed"

    def as_dict(self) -> dict[str, object]:
        return {
            "checks": [check.as_dict() for check in self.checks],
            "schema_version": "mvp-smoke-report-v1",
            "seed_arxiv_id": self.seed_arxiv_id,
            "status": self.status,
        }


def read_private_smoke_token(path: Path) -> str:
    """Read a private bearer token without including its value in errors."""
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise MvpSmokeConfigurationError("Smoke token file is unavailable")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_uid not in {0, os.geteuid()}:
        raise MvpSmokeConfigurationError("Smoke token file permissions are unsafe")
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exception:
        raise MvpSmokeConfigurationError("Smoke token file is unreadable") from exception
    return validate_smoke_token(token)


def validate_smoke_token(token: str) -> str:
    """Reject empty, oversized, or control-character bearer tokens."""
    if (
        not token
        or len(token) > 4096
        or any(not 0x21 <= ord(character) <= 0x7E for character in token)
    ):
        raise MvpSmokeConfigurationError("Smoke token is invalid")
    return token


def _validate_base_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exception:
        raise MvpSmokeConfigurationError("Smoke base URL is invalid") from exception
    del port
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise MvpSmokeConfigurationError("Smoke base URL is invalid")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        address_is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        address_is_loopback = False
    loopback = hostname == "localhost" or address_is_loopback
    if parsed.scheme == "http" and not loopback:
        raise MvpSmokeConfigurationError("Remote smoke targets must use HTTPS")
