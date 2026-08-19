"""Contracts for the local MVP demo-user reset command."""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest

from mneme.cli import reset_demo_user
from mneme.core.config import Settings
from mneme.models.user import User, UserPreference

USER_ID = UUID("00000000-0000-4000-8000-000000000111")

pytestmark = pytest.mark.base


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeSession:
    def __init__(
        self,
        *,
        preference: object | None = None,
        user_exists: bool = True,
    ) -> None:
        self.preference = preference
        self.user_exists = user_exists
        self.committed = False
        self.added: list[object] = []
        self.execute_count = 0

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info

    async def get(self, model: type[object], _key: object) -> object | None:
        if model is User:
            return object() if self.user_exists else None
        if model is UserPreference:
            return self.preference
        raise AssertionError(f"Unexpected model: {model}")

    async def execute(self, _statement: object) -> FakeResult:
        self.execute_count += 1
        return FakeResult(7 if self.execute_count == 1 else 3)

    def add(self, value: object) -> None:
        self.added.append(value)

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


def test_reset_removes_user_state_and_clears_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    preference = SimpleNamespace(
        explicit_topics=["cs.AI"],
        followed_authors=["Ada"],
        behavior_embedding=[0.1],
        negative_behavior_embedding=[0.2],
        behavior_embedding_model="model",
        behavior_confidence=0.8,
        behavior_evidence={"events": 4},
        model_version=2,
        updated_at=None,
    )
    session = FakeSession(preference=preference)
    database = FakeDatabase(session)
    monkeypatch.setattr(reset_demo_user.Database, "from_settings", lambda _: database)

    result = asyncio.run(reset_demo_user.run(settings()))

    assert result.deleted_events == 7
    assert result.deleted_qa_conversations == 3
    assert result.deleted_digests == 3
    assert preference.explicit_topics == []
    assert preference.followed_authors == []
    assert preference.behavior_embedding is None
    assert preference.negative_behavior_embedding is None
    assert preference.behavior_embedding_model is None
    assert preference.behavior_confidence == 0.0
    assert preference.behavior_evidence == {}
    assert preference.model_version == 1
    assert session.committed is True
    assert database.disposed is True


def test_reset_unknown_user_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(user_exists=False)
    database = FakeDatabase(session)
    monkeypatch.setattr(reset_demo_user.Database, "from_settings", lambda _: database)

    with pytest.raises(
        reset_demo_user.DemoResetConfigurationError,
        match=reset_demo_user.UNKNOWN_USER_ERROR,
    ):
        asyncio.run(reset_demo_user.run(settings()))

    assert session.execute_count == 0
    assert session.committed is False
    assert database.disposed is True


def test_reset_missing_user_refuses_before_database_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("database must not be created")

    monkeypatch.setattr(reset_demo_user.Database, "from_settings", unexpected_database)

    with pytest.raises(
        reset_demo_user.DemoResetConfigurationError,
        match=reset_demo_user.MISSING_USER_ERROR,
    ):
        asyncio.run(reset_demo_user.run(Settings(demo_user_id=None, _env_file=None)))
