"""Local safety boundaries for deterministic demo orchestration."""

from __future__ import annotations

import fcntl
import hmac
import os
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mneme.core.config import Settings
from mneme.core.security import token_sha256
from mneme.db.session import Database
from mneme.ops.health_types import PlatformHealthConfigurationError, validate_loopback_url
from mneme.repositories.demo_user_bootstrap import (
    DemoUserBootstrapRepository,
    DemoUserBootstrapResult,
)


class DemoSeedError(RuntimeError):
    """Demo preparation failed without exposing credentials or response bodies."""


class DemoSeedConfigurationError(ValueError):
    """A local demo seed setting is missing or unsafe."""


@dataclass(frozen=True)
class DemoSeedConfig:
    """Bounded local orchestration parameters."""

    base_url: str = "http://127.0.0.1:8000"
    lock_file: Path = Path("/var/lib/mneme/demo-seed.lock")
    request_timeout_seconds: float = 900
    ready_timeout_seconds: float = 900
    poll_interval_seconds: float = 2

    def __post_init__(self) -> None:
        try:
            validate_loopback_url(self.base_url)
        except PlatformHealthConfigurationError as exception:
            raise DemoSeedConfigurationError("Demo seed URL must use loopback") from exception
        if not self.lock_file.is_absolute() or ".." in self.lock_file.parts:
            raise DemoSeedConfigurationError("Demo seed lock path must be absolute")
        if not 30 <= self.request_timeout_seconds <= 1800:
            raise DemoSeedConfigurationError("Demo seed request timeout is invalid")
        if not 30 <= self.ready_timeout_seconds <= 1800:
            raise DemoSeedConfigurationError("Demo seed readiness timeout is invalid")
        if not 0.1 <= self.poll_interval_seconds <= 30:
            raise DemoSeedConfigurationError("Demo seed poll interval is invalid")


@dataclass(frozen=True)
class DemoSeedResult:
    """Non-sensitive result of one initial or resumed seed operation."""

    manifest_id: str
    manifest_sha256: str
    digest_id: str
    seed_paper_id: str
    digest_paper_ids: tuple[str, ...]
    digest_arxiv_ids: tuple[str, ...]
    paper_count: int
    ready_papers: int
    events_accepted: int
    events_duplicates: int
    user_created: bool
    preferences_created: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "digest_id": self.digest_id,
            "digest_arxiv_ids": list(self.digest_arxiv_ids),
            "digest_paper_ids": list(self.digest_paper_ids),
            "events_accepted": self.events_accepted,
            "events_duplicates": self.events_duplicates,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "paper_count": self.paper_count,
            "preferences_created": self.preferences_created,
            "ready_papers": self.ready_papers,
            "schema_version": "demo-seed-result-v1",
            "seed_paper_id": self.seed_paper_id,
            "status": "ok",
            "user_created": self.user_created,
        }


def read_private_demo_token(path: Path, settings: Settings) -> str:
    """Read and verify a private token file without returning it in errors."""
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise DemoSeedConfigurationError("Demo token file is unavailable")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_uid not in {0, os.geteuid()}:
        raise DemoSeedConfigurationError("Demo token file permissions are unsafe")
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exception:
        raise DemoSeedConfigurationError("Demo token file is unreadable") from exception
    if (
        not token
        or len(token) > 4096
        or any(not 0x21 <= ord(character) <= 0x7E for character in token)
    ):
        raise DemoSeedConfigurationError("Demo token is invalid")
    configured = (
        settings.demo_token_sha256.get_secret_value()
        if settings.demo_token_sha256 is not None
        else ""
    )
    if not hmac.compare_digest(token_sha256(token), configured):
        raise DemoSeedConfigurationError("Demo token does not match production configuration")
    return token


async def bootstrap_demo_user(settings: Settings, display_name: str) -> DemoUserBootstrapResult:
    """Create the configured user and preference row idempotently."""
    if settings.demo_user_id is None:
        raise DemoSeedConfigurationError("Demo user ID is not configured")
    database = Database.from_settings(settings, echo=False)
    try:
        async with database.session_factory() as session:
            return await DemoUserBootstrapRepository(session).bootstrap(
                settings.demo_user_id, display_name=display_name
            )
    finally:
        await database.dispose()


@asynccontextmanager
async def demo_seed_lock(path: Path) -> AsyncIterator[None]:
    """Prevent overlapping seed runs on one production host."""
    if path.is_symlink():
        raise DemoSeedConfigurationError("Demo seed lock cannot be a symbolic link")
    if path.parent.is_symlink():
        raise DemoSeedConfigurationError("Demo seed lock directory cannot be a symbolic link")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exception:
            raise DemoSeedError("Another demo seed operation is running") from exception
        yield
    finally:
        os.close(descriptor)
