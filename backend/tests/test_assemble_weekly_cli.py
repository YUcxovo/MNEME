"""CLI contract tests for weekly Research Briefing scheduling."""

import asyncio
import json
from datetime import date
from uuid import UUID

import pytest

from mneme.core.config import Settings
from mneme.tasks import assemble_weekly

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
JOB_ID = UUID("00000000-0000-0000-0000-000000000222")
WEEK_START = date(2026, 7, 20)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeDatabase:
    def __init__(self) -> None:
        self.disposed = False

    def session_factory(self) -> FakeSession:
        return FakeSession()

    async def dispose(self) -> None:
        self.disposed = True


class FakeQueue:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _summary() -> assemble_weekly.WeeklyScheduleSummary:
    return assemble_weekly.WeeklyScheduleSummary(
        user_id=USER_ID,
        week_start=WEEK_START,
        job_id=JOB_ID,
        job_created=True,
        job_requeued=False,
        job_dispatched=True,
        job_unchanged=False,
    )


def test_week_boundary_and_backfill_parser_require_monday() -> None:
    assert assemble_weekly.current_week_start(date(2026, 7, 23)) == WEEK_START
    assert assemble_weekly.build_parser().parse_args([]).week_start is None
    assert (
        assemble_weekly.build_parser()
        .parse_args(["--week-start", WEEK_START.isoformat()])
        .week_start
        == WEEK_START
    )

    with pytest.raises(SystemExit):
        assemble_weekly.build_parser().parse_args(["--week-start", "2026-07-21"])


def test_missing_demo_user_fails_before_infrastructure(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("database should not be constructed")

    monkeypatch.setattr(assemble_weekly, "Database", forbidden)

    with pytest.raises(ValueError, match="MNEME_DEMO_USER_ID"):
        asyncio.run(
            assemble_weekly.run(
                settings=Settings(demo_user_id=None, _env_file=None),
                week_start=WEEK_START,
            )
        )


def test_run_releases_database_and_queue_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    database = FakeDatabase()
    queue = FakeQueue()

    async def fake_create_pool(*args: object, **kwargs: object) -> FakeQueue:
        del args, kwargs
        return queue

    async def fake_schedule(*args: object, **kwargs: object):
        del args, kwargs
        return _summary()

    monkeypatch.setattr(assemble_weekly, "Database", lambda *args, **kwargs: database)
    monkeypatch.setattr(assemble_weekly, "create_pool", fake_create_pool)
    monkeypatch.setattr(assemble_weekly, "schedule_weekly", fake_schedule)

    result = asyncio.run(
        assemble_weekly.run(
            settings=Settings(demo_user_id=USER_ID, _env_file=None),
            week_start=WEEK_START,
        )
    )

    assert result.job_dispatched is True
    assert database.disposed is True
    assert queue.closed is True


def test_cli_emits_machine_readable_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def successful(**kwargs: object):
        del kwargs
        return _summary()

    monkeypatch.setattr(assemble_weekly, "run", successful)
    monkeypatch.setattr("sys.argv", ["assemble_weekly"])

    assemble_weekly.main()

    assert json.loads(capsys.readouterr().out) == {
        "job_created": True,
        "job_dispatched": True,
        "job_id": str(JOB_ID),
        "job_requeued": False,
        "job_unchanged": False,
        "user_id": str(USER_ID),
        "week_start": WEEK_START.isoformat(),
    }


def test_cli_hides_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def unavailable(**kwargs: object):
        del kwargs
        raise ConnectionError("sensitive infrastructure details")

    monkeypatch.setattr(assemble_weekly, "run", unavailable)
    monkeypatch.setattr("sys.argv", ["assemble_weekly"])

    with pytest.raises(SystemExit) as captured:
        assemble_weekly.main()

    assert captured.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "weekly_schedule_unavailable"
    assert "sensitive" not in error["message"]
