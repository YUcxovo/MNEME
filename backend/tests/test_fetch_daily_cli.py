"""CLI contract tests for cron-facing daily metadata scheduling."""

import asyncio
import json
from datetime import date

import pytest

from mneme.core.config import Settings
from mneme.tasks import fetch_daily

RUN_DATE = date(2026, 7, 21)

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


def _summary() -> fetch_daily.DailyScheduleSummary:
    return fetch_daily.DailyScheduleSummary(RUN_DATE, ("cs.AI",), 1, 0, 0, 1)


def test_config_is_multiple_bounded_and_cli_is_zero_argument() -> None:
    settings = Settings(
        arxiv_max_results=50,
        arxiv_daily_categories="cs.CL, cs.AI,cs.CL",
        arxiv_daily_max_results=12,
        _env_file=None,
    )

    assert fetch_daily.build_parser().parse_args([]).categories is None
    assert fetch_daily.validate_request(
        settings,
        categories=settings.daily_arxiv_categories,
        max_results=settings.arxiv_daily_max_results,
    ) == ("cs.CL", "cs.AI")
    with pytest.raises(ValueError, match="page bound"):
        fetch_daily.validate_request(settings, categories=("cs.AI",), max_results=51)


def test_run_releases_database_and_queue_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    database = FakeDatabase()
    queue = FakeQueue()

    async def fake_create_pool(*args: object, **kwargs: object) -> FakeQueue:
        del args, kwargs
        return queue

    async def fake_schedule(*args: object, **kwargs: object) -> fetch_daily.DailyScheduleSummary:
        del args, kwargs
        return _summary()

    monkeypatch.setattr(fetch_daily, "Database", lambda *args, **kwargs: database)
    monkeypatch.setattr(fetch_daily, "create_pool", fake_create_pool)
    monkeypatch.setattr(fetch_daily, "schedule_daily", fake_schedule)

    result = asyncio.run(
        fetch_daily.run(
            settings=Settings(_env_file=None),
            run_date=RUN_DATE,
            categories=("cs.AI",),
            max_results=1,
        )
    )

    assert result.jobs_dispatched == 1
    assert database.disposed is True
    assert queue.closed is True


def test_cli_emits_machine_readable_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def successful(**kwargs: object) -> fetch_daily.DailyScheduleSummary:
        del kwargs
        return _summary()

    monkeypatch.setattr(fetch_daily, "run", successful)
    monkeypatch.setattr("sys.argv", ["fetch_daily"])

    fetch_daily.main()

    assert json.loads(capsys.readouterr().out) == {
        "categories": ["cs.AI"],
        "jobs_created": 1,
        "jobs_dispatched": 1,
        "jobs_requeued": 0,
        "jobs_unchanged": 0,
        "run_date": RUN_DATE.isoformat(),
    }


def test_cli_hides_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def unavailable(**kwargs: object) -> fetch_daily.DailyScheduleSummary:
        del kwargs
        raise ConnectionError("sensitive infrastructure details")

    monkeypatch.setattr(fetch_daily, "run", unavailable)
    monkeypatch.setattr("sys.argv", ["fetch_daily"])

    with pytest.raises(SystemExit) as captured:
        fetch_daily.main()

    assert captured.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "daily_schedule_unavailable"
    assert "sensitive" not in error["message"]
