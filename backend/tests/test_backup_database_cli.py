"""CLI contract tests for local PostgreSQL backups."""

import json
from datetime import UTC, datetime

import pytest

from mneme.cli import backup_database
from mneme.ops.backup import BackupConfigurationError, BackupError, BackupManifest

NOW = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)


def _manifest() -> BackupManifest:
    return BackupManifest(
        archive="mneme-20260803T100000000000Z.dump",
        completed_at=NOW,
        sha256="a" * 64,
        size_bytes=1024,
    )


@pytest.mark.base
def test_backup_cli_prints_safe_manifest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(backup_database, "validate_libpq_environment", lambda _env: None)
    monkeypatch.setattr(backup_database, "run_database_backup", lambda _config: _manifest())
    monkeypatch.setattr("sys.argv", ["backup_database"])

    backup_database.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "mneme-backup-v1"
    assert payload["verification"] == "pg_restore_list"
    assert payload["status"] == "ok"


@pytest.mark.base
@pytest.mark.parametrize(
    ("error", "exit_code", "error_code"),
    [
        (BackupConfigurationError("secret config"), 2, backup_database.CONFIG_ERROR),
        (BackupError("postgresql://user:secret@db"), 1, backup_database.BACKUP_ERROR),
    ],
)
def test_backup_cli_redacts_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    error_code: str,
) -> None:
    monkeypatch.setattr(backup_database, "validate_libpq_environment", lambda _env: None)

    def failed(_config: object) -> BackupManifest:
        raise error

    monkeypatch.setattr(backup_database, "run_database_backup", failed)
    monkeypatch.setattr("sys.argv", ["backup_database"])

    with pytest.raises(SystemExit) as captured:
        backup_database.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == exit_code
    assert payload["error"] == error_code
    assert "secret" not in json.dumps(payload)


@pytest.mark.base
def test_backup_cli_rejects_invalid_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["backup_database", "--retention-count", "not-an-int"])

    with pytest.raises(SystemExit) as captured:
        backup_database.main()

    assert captured.value.code == 2
    assert json.loads(capsys.readouterr().err)["error"] == backup_database.CONFIG_ERROR
