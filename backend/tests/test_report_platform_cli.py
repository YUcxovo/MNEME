"""CLI contract tests for the bounded platform operations report."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from mneme.cli import report_platform
from mneme.core.config import Settings

NOW = datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-0000-0000-000000000123")


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": "platform-operations-v1",
        "generated_at": NOW,
        "window": {"start": NOW, "end": NOW, "hours": 24},
        "jobs": {
            "created": 1,
            "recent_failures": [
                {
                    "job_id": JOB_ID,
                    "stage": "parse_pdf",
                    "error_code": "parse_failed",
                    "attempt_count": 2,
                    "created_at": NOW,
                    "started_at": NOW,
                    "finished_at": NOW,
                }
            ],
        },
        "papers": {"total": 5},
        "digests": {"generated": 1},
    }


@pytest.mark.base
@pytest.mark.db
def test_parser_defaults_and_bounds() -> None:
    arguments = report_platform.build_parser().parse_args([])
    assert (arguments.window_hours, arguments.dispatch_lease_seconds, arguments.failed_limit) == (
        24,
        300,
        20,
    )

    report_platform.validate_bounds(
        window_hours=720,
        dispatch_lease_seconds=1,
        failed_limit=0,
    )
    with pytest.raises(report_platform.PlatformReportInputError):
        report_platform.validate_bounds(
            window_hours=721,
            dispatch_lease_seconds=300,
            failed_limit=20,
        )
    with pytest.raises(report_platform.PlatformReportInputError):
        report_platform.validate_bounds(
            window_hours=24,
            dispatch_lease_seconds=86401,
            failed_limit=20,
        )


@pytest.mark.base
@pytest.mark.db
def test_run_disposes_database_and_forwards_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakeDatabase:
        instance: "FakeDatabase | None" = None

        def __init__(self) -> None:
            self.disposed = False
            type(self).instance = self

        @classmethod
        def from_settings(cls, _settings: Settings, *, echo: bool) -> "FakeDatabase":
            assert echo is False
            return cls()

        def session_factory(self) -> FakeSessionContext:
            return FakeSessionContext()

        async def dispose(self) -> None:
            self.disposed = True

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def snapshot(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return _snapshot()

    monkeypatch.setattr(report_platform, "Database", FakeDatabase)
    monkeypatch.setattr(report_platform, "PlatformOperationsRepository", FakeRepository)

    result = asyncio.run(
        report_platform.run(
            Settings(_env_file=None),
            window_hours=12,
            dispatch_lease_seconds=90,
            failed_limit=4,
            now=NOW,
        )
    )

    assert result["schema_version"] == "platform-operations-v1"
    assert calls == [
        {
            "now": NOW,
            "window_hours": 12,
            "dispatch_lease_seconds": 90,
            "failed_limit": 4,
        }
    ]
    assert FakeDatabase.instance is not None
    assert FakeDatabase.instance.disposed


@pytest.mark.base
@pytest.mark.db
def test_cli_serializes_safe_sorted_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def successful(*_args: object, **_kwargs: object) -> dict[str, object]:
        return _snapshot()

    monkeypatch.setattr(report_platform, "run", successful)
    monkeypatch.setattr(report_platform, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sys.argv", ["report_platform"])

    report_platform.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "platform-operations-v1"
    assert payload["jobs"]["recent_failures"][0]["job_id"] == str(JOB_ID)
    assert "last_error" not in json.dumps(payload)


@pytest.mark.base
@pytest.mark.db
@pytest.mark.parametrize(
    ("argv", "exit_code", "error_code"),
    [
        (["--window-hours", "0"], 2, report_platform.INPUT_ERROR),
        (["--failed-limit", "not-an-integer"], 2, report_platform.INPUT_ERROR),
    ],
)
def test_cli_returns_json_for_invalid_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    exit_code: int,
    error_code: str,
) -> None:
    monkeypatch.setattr("sys.argv", ["report_platform", *argv])

    with pytest.raises(SystemExit) as captured:
        report_platform.main()

    assert captured.value.code == exit_code
    assert json.loads(capsys.readouterr().err)["error"] == error_code


@pytest.mark.base
@pytest.mark.db
def test_cli_hides_infrastructure_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ConnectionError("sensitive database address")

    monkeypatch.setattr(report_platform, "run", unavailable)
    monkeypatch.setattr(report_platform, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sys.argv", ["report_platform"])

    with pytest.raises(SystemExit) as captured:
        report_platform.main()

    error = json.loads(capsys.readouterr().err)
    assert captured.value.code == 1
    assert error["error"] == report_platform.UNAVAILABLE_ERROR
    assert "sensitive" not in json.dumps(error)
