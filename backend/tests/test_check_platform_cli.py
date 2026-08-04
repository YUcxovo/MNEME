"""CLI contract tests for private platform health."""

import json
from datetime import UTC, datetime

import pytest

from mneme.cli import check_platform
from mneme.ops.health_types import (
    HealthCheck,
    HealthCheckStatus,
    PlatformHealthReport,
)

NOW = datetime(2026, 8, 3, 12, tzinfo=UTC)


@pytest.mark.base
def test_health_cli_prints_report_and_operational_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = PlatformHealthReport(
        checks=(HealthCheck("api_liveness", HealthCheckStatus.FAIL, "failed"),),
        generated_at=NOW,
    )

    async def unhealthy(*_args: object, **_kwargs: object) -> PlatformHealthReport:
        return report

    monkeypatch.setattr(check_platform, "run_platform_health", unhealthy)
    monkeypatch.setattr("sys.argv", ["check_platform"])

    with pytest.raises(SystemExit) as captured:
        check_platform.main()

    payload = json.loads(capsys.readouterr().out)
    assert captured.value.code == 1
    assert payload["schema_version"] == "platform-health-v1"
    assert payload["status"] == "unhealthy"


@pytest.mark.base
def test_health_cli_redacts_invalid_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_url = "http://user:secret@127.0.0.1:8000"
    monkeypatch.setattr("sys.argv", ["check_platform", "--base-url", secret_url])

    with pytest.raises(SystemExit) as captured:
        check_platform.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == 2
    assert payload["error"] == check_platform.CONFIG_ERROR
    assert "secret" not in json.dumps(payload)
