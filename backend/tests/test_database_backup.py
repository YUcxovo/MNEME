"""Tests for secure local PostgreSQL backups."""

import hashlib
import json
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mneme.ops.backup import (
    BackupBusyError,
    BackupConfig,
    BackupConfigurationError,
    BackupError,
    run_backup_command,
    run_database_backup,
    validate_libpq_environment,
)

NOW = datetime(2026, 8, 3, 10, 11, 12, 123456, tzinfo=UTC)
ARCHIVE_BYTES = b"PGDMP\x01\x0f\x00validated-test-archive"


class FakeCommandRunner:
    def __init__(self, *, fail_command: str | None = None) -> None:
        self.fail_command = fail_command
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def __call__(self, arguments: tuple[str, ...], timeout_seconds: int) -> None:
        self.calls.append((arguments, timeout_seconds))
        if arguments[0] == self.fail_command:
            raise BackupError("postgresql://user:secret@db")
        if arguments[0] == "pg_dump":
            output = next(
                item.removeprefix("--file=") for item in arguments if item.startswith("--file=")
            )
            Path(output).write_bytes(ARCHIVE_BYTES)
        elif arguments[0] == "pg_restore":
            assert Path(arguments[-1]).read_bytes() == ARCHIVE_BYTES


@pytest.mark.base
def test_database_backup_creates_verified_atomic_manifest(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    config = BackupConfig(output_dir=tmp_path, retention_count=3)

    manifest = run_database_backup(config, now=NOW, runner=runner)

    archive = tmp_path / manifest.archive
    manifest_path = archive.with_suffix(".json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert archive.read_bytes() == ARCHIVE_BYTES
    assert payload == manifest.as_dict()
    assert json.loads((tmp_path / "latest.json").read_text(encoding="utf-8")) == payload
    assert payload["sha256"] == hashlib.sha256(ARCHIVE_BYTES).hexdigest()
    assert payload["verification"] == "pg_restore_list"
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert [call[0][0] for call in runner.calls] == ["pg_dump", "pg_restore"]
    assert "--format=custom" in runner.calls[0][0]
    assert "--no-password" in runner.calls[0][0]
    assert all("postgresql" not in " ".join(arguments) for arguments, _ in runner.calls)
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.base
@pytest.mark.parametrize("failed_command", ["pg_dump", "pg_restore"])
def test_database_backup_removes_partial_files_on_command_failure(
    tmp_path: Path, failed_command: str
) -> None:
    with pytest.raises(BackupError):
        run_database_backup(
            BackupConfig(output_dir=tmp_path),
            now=NOW,
            runner=FakeCommandRunner(fail_command=failed_command),
        )

    assert not list(tmp_path.glob("*.partial"))
    assert not list(tmp_path.glob("*.dump"))
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.base
def test_backup_retention_ignores_unrelated_and_symlinked_files(tmp_path: Path) -> None:
    unrelated = tmp_path / "keep-me.dump"
    unrelated.write_text("unrelated", encoding="utf-8")
    external = tmp_path.parent / "external.dump"
    external.write_text("external", encoding="utf-8")
    malicious_manifest = tmp_path / "mneme-20000101T000000000000Z.json"
    malicious_manifest.symlink_to(external)

    for offset in range(4):
        run_database_backup(
            BackupConfig(output_dir=tmp_path, retention_count=2),
            now=NOW + timedelta(seconds=offset),
            runner=FakeCommandRunner(),
        )

    assert len(list(tmp_path.glob("mneme-*.dump"))) == 2
    assert len([path for path in tmp_path.glob("mneme-*.json") if not path.is_symlink()]) == 2
    assert unrelated.read_text(encoding="utf-8") == "unrelated"
    assert external.read_text(encoding="utf-8") == "external"
    assert malicious_manifest.is_symlink()


@pytest.mark.base
def test_backup_lock_rejects_a_concurrent_run(tmp_path: Path) -> None:
    nested_error: BackupBusyError | None = None

    def runner(arguments: tuple[str, ...], timeout_seconds: int) -> None:
        nonlocal nested_error
        del timeout_seconds
        if arguments[0] == "pg_dump":
            try:
                run_database_backup(
                    BackupConfig(output_dir=tmp_path),
                    now=NOW + timedelta(seconds=1),
                    runner=FakeCommandRunner(),
                )
            except BackupBusyError as error:
                nested_error = error
            output = next(
                item.removeprefix("--file=") for item in arguments if item.startswith("--file=")
            )
            Path(output).write_bytes(ARCHIVE_BYTES)

    run_database_backup(BackupConfig(output_dir=tmp_path), now=NOW, runner=runner)
    assert nested_error is not None


@pytest.mark.base
def test_libpq_environment_requires_private_regular_files(tmp_path: Path) -> None:
    service_file = tmp_path / "pg_service.conf"
    password_file = tmp_path / "pgpass"
    service_file.write_text("service", encoding="utf-8")
    password_file.write_text("password", encoding="utf-8")
    service_file.chmod(0o600)
    password_file.chmod(0o600)
    environment = {
        "PGSERVICE": "mneme-backup",
        "PGSERVICEFILE": str(service_file),
        "PGPASSFILE": str(password_file),
    }

    validate_libpq_environment(environment)

    password_file.chmod(0o644)
    with pytest.raises(BackupConfigurationError):
        validate_libpq_environment(environment)


@pytest.mark.base
@pytest.mark.parametrize(
    "values",
    [
        {"output_dir": Path("relative")},
        {"output_dir": Path("/tmp/backup"), "retention_count": 0},
        {"output_dir": Path("/tmp/backup"), "timeout_seconds": 29},
        {"output_dir": Path("/tmp/backup"), "lock_wait_timeout_seconds": 301},
    ],
)
def test_backup_config_rejects_unsafe_bounds(values: dict[str, object]) -> None:
    with pytest.raises(BackupConfigurationError):
        BackupConfig(**values)  # type: ignore[arg-type]


@pytest.mark.base
def test_backup_command_hides_subprocess_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("postgresql://user:secret@db", 30)

    monkeypatch.setattr(subprocess, "run", timed_out)

    with pytest.raises(BackupError) as captured:
        run_backup_command(("pg_dump",), 30)

    assert "secret" not in str(captured.value)
