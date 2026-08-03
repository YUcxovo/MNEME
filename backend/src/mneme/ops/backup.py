"""Secure local PostgreSQL backup creation and retention."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from mneme.ops.backup_retention import apply_retention

_SERVICE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")


class BackupError(RuntimeError):
    """A backup could not be completed safely."""


class BackupConfigurationError(ValueError):
    """Backup configuration is missing or unsafe."""


class BackupBusyError(BackupError):
    """Another backup process currently owns the host lock."""


class BackupCommandRunner(Protocol):
    """Subprocess boundary injected by unit tests."""

    def __call__(self, arguments: tuple[str, ...], timeout_seconds: int) -> None: ...


@dataclass(frozen=True)
class BackupConfig:
    """Bounded local backup policy."""

    output_dir: Path
    retention_count: int = 7
    timeout_seconds: int = 900
    lock_wait_timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not self.output_dir.is_absolute() or ".." in self.output_dir.parts:
            raise BackupConfigurationError("Backup output directory must be absolute")
        if not 1 <= self.retention_count <= 90:
            raise BackupConfigurationError("Backup retention must be between 1 and 90")
        if not 30 <= self.timeout_seconds <= 7200:
            raise BackupConfigurationError("Backup timeout must be between 30 and 7200 seconds")
        if not 1 <= self.lock_wait_timeout_seconds <= 300:
            raise BackupConfigurationError("Database lock wait must be between 1 and 300 seconds")


@dataclass(frozen=True)
class BackupManifest:
    """Non-sensitive evidence for one locally validated archive."""

    archive: str
    completed_at: datetime
    sha256: str
    size_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "archive": self.archive,
            "completed_at": self.completed_at.isoformat().replace("+00:00", "Z"),
            "schema_version": "mneme-backup-v1",
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "verification": "pg_restore_list",
        }


def validate_libpq_environment(environment: Mapping[str, str]) -> None:
    """Require indirect libpq connection files without reading their contents."""
    service = environment.get("PGSERVICE", "")
    if not _SERVICE_PATTERN.fullmatch(service):
        raise BackupConfigurationError("PGSERVICE must name a configured libpq service")
    for key in ("PGSERVICEFILE", "PGPASSFILE"):
        raw_path = environment.get(key, "")
        path = Path(raw_path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise BackupConfigurationError(f"{key} must reference a regular absolute file")
        metadata = path.stat()
        if stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_uid not in {0, os.geteuid()}:
            raise BackupConfigurationError(f"{key} permissions or ownership are unsafe")


def run_database_backup(
    config: BackupConfig,
    *,
    now: datetime | None = None,
    runner: BackupCommandRunner | None = None,
) -> BackupManifest:
    """Create, validate, record, and retain one custom-format PostgreSQL archive."""
    completed_at = now or datetime.now(UTC)
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise BackupConfigurationError("Backup time must include a timezone")
    completed_at = completed_at.astimezone(UTC)
    command_runner = runner or run_backup_command
    _prepare_output_directory(config.output_dir)

    with _backup_lock(config.output_dir / ".backup.lock"):
        archive_name = f"mneme-{completed_at.strftime('%Y%m%dT%H%M%S%fZ')}.dump"
        archive_path = config.output_dir / archive_name
        manifest_path = archive_path.with_suffix(".json")
        if archive_path.exists() or manifest_path.exists():
            raise BackupError("A backup already exists for this timestamp")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{archive_name}.", suffix=".partial", dir=config.output_dir
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            command_runner(
                (
                    "pg_dump",
                    "--format=custom",
                    f"--file={temporary_path}",
                    "--no-password",
                    f"--lock-wait-timeout={config.lock_wait_timeout_seconds}s",
                ),
                config.timeout_seconds,
            )
            command_runner(
                ("pg_restore", "--list", str(temporary_path)),
                config.timeout_seconds,
            )
            size_bytes = temporary_path.stat().st_size
            if size_bytes < 1:
                raise BackupError("PostgreSQL produced an empty archive")
            checksum = _sha256_file(temporary_path)
            temporary_path.chmod(0o600)
            _fsync_file(temporary_path)
            temporary_path.replace(archive_path)
            _fsync_directory(config.output_dir)

            manifest = BackupManifest(
                archive=archive_name,
                completed_at=completed_at,
                sha256=checksum,
                size_bytes=size_bytes,
            )
            _atomic_json_write(manifest_path, manifest.as_dict())
            _atomic_json_write(config.output_dir / "latest.json", manifest.as_dict())
            apply_retention(config.output_dir, config.retention_count)
            return manifest
        finally:
            temporary_path.unlink(missing_ok=True)


def run_backup_command(arguments: tuple[str, ...], timeout_seconds: int) -> None:
    """Run one bounded PostgreSQL client command without a shell."""
    try:
        result = subprocess.run(
            arguments,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exception:
        raise BackupError("A PostgreSQL backup command was unavailable") from exception
    if result.returncode != 0:
        raise BackupError("A PostgreSQL backup command failed")


def _prepare_output_directory(path: Path) -> None:
    if path.is_symlink():
        raise BackupConfigurationError("Backup output directory cannot be a symbolic link")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.chmod(0o700)
    if not path.is_dir():
        raise BackupConfigurationError("Backup output location is not a directory")


@contextmanager
def _backup_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exception:
            raise BackupBusyError("Another backup is already running") from exception
        yield
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json_write(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
        _fsync_directory(path.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
