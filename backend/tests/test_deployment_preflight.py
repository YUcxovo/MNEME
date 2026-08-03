"""Tests for the production deployment preflight gate."""

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from mneme.cli import preflight_deployment as preflight_cli
from mneme.core.config import Settings
from mneme.ops import preflight_probe
from mneme.ops.preflight import (
    CheckStatus,
    PreflightCheck,
    PreflightReport,
    run_preflight,
    static_preflight_checks,
)
from mneme.ops.preflight_probe import expected_migration_head

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "debug": False,
        "log_level": "INFO",
        "database_url": "postgresql+asyncpg://mneme:secret@db.internal/mneme",
        "paper_storage_dir": Path("/var/lib/mneme/papers"),
        "demo_token_sha256": "a" * 64,
        "demo_user_id": USER_ID,
        "anthropic_api_key": "anthropic-secret",
        "openai_api_key": "openai-secret",
    }
    values.update(overrides)
    return Settings.model_validate(values)


class FakeProbe:
    def __init__(self, **overrides: object) -> None:
        self.values: dict[str, object] = {
            "ping_database": True,
            "database_revision": "0007",
            "has_pgvector": True,
            "demo_user_exists": True,
            "connection_limits": (100, 3, 2),
            "ping_redis": True,
            "paper_storage_writable": True,
            "backup_tools_available": True,
            "backup_credentials_configured": True,
            "backup_target_matches_database": True,
            "aclose": True,
        }
        self.values.update(overrides)
        self.closed = False

    async def _get(self, name: str) -> object:
        value = self.values[name]
        if isinstance(value, Exception):
            raise value
        return value

    async def ping_database(self) -> bool:
        return bool(await self._get("ping_database"))

    async def database_revision(self) -> str | None:
        value = await self._get("database_revision")
        return str(value) if value is not None else None

    async def has_pgvector(self) -> bool:
        return bool(await self._get("has_pgvector"))

    async def demo_user_exists(self, user_id: UUID) -> bool:
        assert user_id == USER_ID
        return bool(await self._get("demo_user_exists"))

    async def connection_limits(self) -> tuple[int, int, int]:
        value = await self._get("connection_limits")
        assert isinstance(value, tuple)
        return value

    async def ping_redis(self) -> bool:
        return bool(await self._get("ping_redis"))

    async def paper_storage_writable(self) -> bool:
        return bool(await self._get("paper_storage_writable"))

    async def backup_tools_available(self) -> bool:
        return bool(await self._get("backup_tools_available"))

    async def backup_credentials_configured(self) -> bool:
        return bool(await self._get("backup_credentials_configured"))

    async def backup_target_matches_database(self) -> bool:
        return bool(await self._get("backup_target_matches_database"))

    async def aclose(self) -> None:
        self.closed = True
        await self._get("aclose")


@pytest.mark.base
def test_static_preflight_accepts_complete_production_configuration() -> None:
    checks = static_preflight_checks(_settings())

    assert [check.id for check in checks] == [
        "production_mode",
        "loopback_binding",
        "graceful_timeout",
        "service_timeouts",
        "demo_identity",
        "provider_routes",
        "database_configuration",
        "paper_storage_configuration",
    ]
    assert all(check.status is CheckStatus.PASS for check in checks)


@pytest.mark.base
@pytest.mark.parametrize(
    ("overrides", "failed_check"),
    [
        ({"environment": "development"}, "production_mode"),
        ({"debug": True}, "production_mode"),
        ({"log_level": "DEBUG"}, "production_mode"),
        ({"api_graceful_timeout_seconds": 30}, "graceful_timeout"),
        ({"api_graceful_timeout_seconds": 91}, "service_timeouts"),
        ({"arq_job_timeout_seconds": 301}, "service_timeouts"),
        ({"demo_token_sha256": "not-a-digest"}, "demo_identity"),
        ({"demo_user_id": None}, "demo_identity"),
        ({"anthropic_api_key": None}, "provider_routes"),
        ({"anthropic_api_key": "   "}, "provider_routes"),
        ({"anthropic_api_key": "replace-me"}, "provider_routes"),
        ({"openai_api_key": None}, "provider_routes"),
        ({"openai_api_key": "your-key-here"}, "provider_routes"),
        ({"llm_qa_model": "<replace-me>"}, "provider_routes"),
        (
            {"database_url": "postgresql+asyncpg://postgres:postgres@localhost/mneme"},
            "database_configuration",
        ),
        ({"paper_storage_dir": Path(".data/papers")}, "paper_storage_configuration"),
    ],
)
def test_static_preflight_fails_closed(overrides: dict[str, object], failed_check: str) -> None:
    checks = {check.id: check for check in static_preflight_checks(_settings(**overrides))}
    assert checks[failed_check].status is CheckStatus.FAIL


@pytest.mark.base
def test_offline_preflight_records_skipped_live_checks() -> None:
    report = asyncio.run(run_preflight(_settings(), expected_head="unused", offline=True, now=NOW))

    assert report.status == "incomplete"
    assert report.checks[-1].id == "live_dependencies"
    assert report.checks[-1].status is CheckStatus.WARN
    assert report.as_dict()["generated_at"] == "2026-08-03T09:00:00Z"


@pytest.mark.base
def test_live_preflight_reports_capacity_and_closes_probe() -> None:
    probe = FakeProbe()

    report = asyncio.run(run_preflight(_settings(), expected_head="0007", probe=probe, now=NOW))

    assert report.status == "ready"
    assert probe.closed
    capacity = next(check for check in report.checks if check.id == "database_capacity")
    assert capacity.details == {"available": 95, "headroom": 19, "required": 40}
    assert report.as_dict()["counts"] == {"fail": 0, "pass": 18, "warn": 0}


@pytest.mark.base
@pytest.mark.parametrize(
    ("overrides", "failed_check"),
    [
        ({"ping_database": False}, "postgresql"),
        ({"database_revision": "old"}, "migration_head"),
        ({"has_pgvector": False}, "pgvector_extension"),
        ({"demo_user_exists": False}, "demo_user"),
        ({"connection_limits": (45, 3, 2)}, "database_capacity"),
        ({"ping_redis": False}, "redis"),
        ({"paper_storage_writable": False}, "paper_storage"),
        ({"backup_tools_available": False}, "backup_tools"),
        ({"backup_credentials_configured": False}, "backup_credentials"),
        ({"backup_target_matches_database": False}, "backup_target"),
        ({"aclose": RuntimeError("redis://secret")}, "probe_cleanup"),
        ({"ping_database": ConnectionError("postgresql://secret")}, "postgresql"),
    ],
)
def test_live_preflight_contains_dependency_failures(
    overrides: dict[str, object], failed_check: str
) -> None:
    report = asyncio.run(
        run_preflight(
            _settings(),
            expected_head="0007",
            probe=FakeProbe(**overrides),
            now=NOW,
        )
    )
    checks = {check.id: check for check in report.checks}

    assert report.status == "failed"
    assert checks[failed_check].status is CheckStatus.FAIL
    serialized = json.dumps(report.as_dict())
    assert "postgresql://secret" not in serialized
    assert "redis://secret" not in serialized
    assert "anthropic-secret" not in serialized


@pytest.mark.base
def test_expected_migration_head_matches_checkout() -> None:
    config_path = Path(__file__).parents[1] / "alembic.ini"
    assert expected_migration_head(config_path) == "0007"


@pytest.mark.base
def test_backup_database_fingerprint_uses_private_libpq_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout="a" * 32 + "\n", stderr="")

    monkeypatch.setattr(preflight_probe.subprocess, "run", run)
    query = preflight_probe._database_fingerprint_query(USER_ID)

    assert preflight_probe._read_backup_database_fingerprint(query, 2.0) == "a" * 32
    assert captured[0][0] == "psql"
    assert not any("postgresql://" in argument for argument in captured[0])


@pytest.mark.base
def test_backup_database_fingerprint_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(arguments: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, stdout="unexpected\n", stderr="")

    monkeypatch.setattr(preflight_probe.subprocess, "run", run)

    assert preflight_probe._read_backup_database_fingerprint("SELECT 1", 2.0) is None


@pytest.mark.base
def test_preflight_cli_prints_report_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = PreflightReport(
        checks=(PreflightCheck("production_mode", CheckStatus.FAIL, "failed"),),
        generated_at=NOW,
    )

    async def failed_preflight(*_args: object, **_kwargs: object) -> PreflightReport:
        return report

    monkeypatch.setattr(preflight_cli, "get_settings", _settings)
    monkeypatch.setattr(preflight_cli, "expected_migration_head", lambda _path: "0007")
    monkeypatch.setattr(preflight_cli, "run_preflight", failed_preflight)
    monkeypatch.setattr("sys.argv", ["preflight_deployment"])

    with pytest.raises(SystemExit) as captured:
        preflight_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert captured.value.code == 1
    assert payload["schema_version"] == "deployment-preflight-v1"
    assert payload["status"] == "failed"


@pytest.mark.base
def test_preflight_cli_redacts_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_settings() -> Settings:
        raise ValueError("postgresql://user:secret@db")

    monkeypatch.setattr(preflight_cli, "get_settings", invalid_settings)
    monkeypatch.setattr("sys.argv", ["preflight_deployment", "--offline"])

    with pytest.raises(SystemExit) as captured:
        preflight_cli.main()

    error = json.loads(capsys.readouterr().err)
    assert captured.value.code == 2
    assert error["error"] == preflight_cli.CONFIG_ERROR
    assert "secret" not in json.dumps(error)


@pytest.mark.base
def test_preflight_cli_offline_report_is_not_deployment_ready(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(preflight_cli, "get_settings", _settings)
    monkeypatch.setattr("sys.argv", ["preflight_deployment", "--offline"])

    with pytest.raises(SystemExit) as captured:
        preflight_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert captured.value.code == 1
    assert payload["status"] == "incomplete"
