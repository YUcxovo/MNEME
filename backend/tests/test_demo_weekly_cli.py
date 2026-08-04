"""Contracts for the local MVP weekly-briefing command."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from mneme.cli import prepare_demo_weekly
from mneme.core.config import Settings
from mneme.models.digest import DigestType
from mneme.models.user import UserPreference

USER_ID = UUID("00000000-0000-4000-8000-000000000111")
DIGEST_ID = UUID("00000000-0000-4000-8000-000000000222")

pytestmark = pytest.mark.base


class FakeSession:
    def __init__(
        self,
        *,
        preference: object | None = None,
        seed_completed: bool = True,
    ) -> None:
        self.preference = preference
        self.seed_completed = seed_completed
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info

    async def get(self, model: type[object], _key: object) -> object | None:
        if model is UserPreference:
            return self.preference
        raise AssertionError(f"Unexpected model: {model}")

    async def scalar(self, _statement: object) -> bool:
        return self.seed_completed

    async def commit(self) -> None:
        self.committed = True


class FakeDatabase:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.disposed = False

    def session_factory(self) -> FakeSession:
        return self.session

    async def dispose(self) -> None:
        self.disposed = True


def settings() -> Settings:
    return Settings(demo_user_id=USER_ID, _env_file=None)


def test_prepare_weekly_reuses_production_recommender(monkeypatch: pytest.MonkeyPatch) -> None:
    preference = SimpleNamespace(
        explicit_topics=["cs.AI"],
        updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    session = FakeSession(preference=preference)
    database = FakeDatabase(session)
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, repository: object, **kwargs: object) -> None:
            captured["repository"] = repository
            captured.update(kwargs)

        async def generate(self, user_id: UUID, **kwargs: object) -> object:
            captured["user_id"] = user_id
            captured.update(kwargs)
            return SimpleNamespace(
                digest=SimpleNamespace(id=DIGEST_ID),
                entries=[
                    SimpleNamespace(relevance_score=0.81),
                    SimpleNamespace(relevance_score=0.93),
                ],
            )

    monkeypatch.setattr(prepare_demo_weekly.Database, "from_settings", lambda _: database)
    monkeypatch.setattr(prepare_demo_weekly, "RecommendedDigestService", FakeService)

    result = asyncio.run(prepare_demo_weekly.run(settings()))

    assert result.digest_id == DIGEST_ID
    assert result.entry_count == 2
    assert result.maximum_relevance == 0.93
    assert captured["user_id"] == USER_ID
    assert captured["digest_type"] is DigestType.WEEKLY
    assert isinstance(captured["as_of"], datetime)
    assert captured["as_of"].tzinfo is not None
    assert session.committed is True
    assert database.disposed is True


@pytest.mark.parametrize(
    ("topics", "seed_completed"),
    [([], True), (["cs.AI"], False)],
)
def test_prepare_weekly_requires_seed_onboarding(
    monkeypatch: pytest.MonkeyPatch,
    topics: list[str],
    seed_completed: bool,
) -> None:
    preference = SimpleNamespace(
        explicit_topics=topics,
        updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    database = FakeDatabase(FakeSession(preference=preference, seed_completed=seed_completed))
    monkeypatch.setattr(prepare_demo_weekly.Database, "from_settings", lambda _: database)

    with pytest.raises(
        prepare_demo_weekly.DemoWeeklyConfigurationError,
        match=prepare_demo_weekly.SEED_REQUIRED_ERROR,
    ):
        asyncio.run(prepare_demo_weekly.run(settings()))

    assert database.disposed is True


def test_prepare_weekly_missing_user_refuses_before_database_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("database must not be created")

    monkeypatch.setattr(prepare_demo_weekly.Database, "from_settings", unexpected_database)

    with pytest.raises(
        prepare_demo_weekly.DemoWeeklyConfigurationError,
        match=prepare_demo_weekly.MISSING_USER_ERROR,
    ):
        asyncio.run(prepare_demo_weekly.run(Settings(demo_user_id=None, _env_file=None)))


def test_prepare_weekly_cli_reports_safe_seed_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def missing_seed(_settings: Settings) -> prepare_demo_weekly.DemoWeeklyResult:
        raise prepare_demo_weekly.DemoWeeklyConfigurationError(
            prepare_demo_weekly.SEED_REQUIRED_ERROR
        )

    monkeypatch.setattr(prepare_demo_weekly, "run", missing_seed)

    with pytest.raises(SystemExit) as error:
        prepare_demo_weekly.main()

    assert error.value.code == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": prepare_demo_weekly.SEED_REQUIRED_ERROR,
        "status": "error",
    }


def test_prepare_weekly_cli_emits_only_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def successful_run(_settings: Settings) -> prepare_demo_weekly.DemoWeeklyResult:
        return prepare_demo_weekly.DemoWeeklyResult(
            digest_id=DIGEST_ID,
            entry_count=5,
            maximum_relevance=0.91,
        )

    monkeypatch.setattr(prepare_demo_weekly, "run", successful_run)
    monkeypatch.setattr(prepare_demo_weekly, "get_settings", settings)

    prepare_demo_weekly.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "digest_id": str(DIGEST_ID),
        "entry_count": 5,
        "maximum_relevance": 0.91,
        "status": "ok",
    }
    assert "token" not in payload
