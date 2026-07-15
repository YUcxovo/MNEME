"""Tests for safe, idempotent demo-user provisioning."""

import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.cli import bootstrap_demo_user
from mneme.cli.bootstrap_demo_user import DemoUserConfigurationError
from mneme.core.config import Settings
from mneme.repositories.demo_user_bootstrap import (
    DemoUserBootstrapRepository,
    normalize_display_name,
)


def result_with_scalar(value: UUID | None) -> MagicMock:
    """Return a minimal SQLAlchemy result double."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def session_with_results(*values: UUID | None) -> Mock:
    """Return an async-session double with a transaction context."""
    session = Mock(spec=AsyncSession)
    session.begin.return_value = AsyncMock()
    session.execute = AsyncMock(side_effect=[result_with_scalar(value) for value in values])
    return session


@pytest.mark.base
@pytest.mark.db
def test_bootstrap_uses_one_transaction_and_insert_only_conflicts() -> None:
    user_id = uuid4()
    session = session_with_results(user_id, user_id)
    repository = DemoUserBootstrapRepository(cast(AsyncSession, session))

    outcome = asyncio.run(repository.bootstrap(user_id, display_name="  Demo   Researcher "))

    assert outcome.user_id == user_id
    assert outcome.user_created
    assert outcome.preferences_created
    session.begin.assert_called_once_with()
    assert session.execute.await_count == 2

    user_statement, preference_statement = (
        call.args[0] for call in session.execute.await_args_list
    )
    user_sql = str(user_statement.compile(dialect=postgresql.dialect()))
    preference_sql = str(preference_statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT pk_users DO NOTHING" in user_sql
    assert "ON CONFLICT ON CONSTRAINT pk_user_preferences DO NOTHING" in preference_sql
    assert "DO UPDATE" not in user_sql
    assert "DO UPDATE" not in preference_sql
    assert user_statement.compile().params["display_name"] == "Demo Researcher"
    preference_params = preference_statement.compile().params
    assert preference_params["explicit_topics"] == []
    assert preference_params["followed_authors"] == []
    assert preference_params["model_version"] == 1


@pytest.mark.base
@pytest.mark.db
def test_repeat_bootstrap_reports_existing_rows_without_overwriting() -> None:
    user_id = uuid4()
    session = session_with_results(None, None)
    repository = DemoUserBootstrapRepository(cast(AsyncSession, session))

    outcome = asyncio.run(repository.bootstrap(user_id, display_name="Different Name"))

    assert not outcome.user_created
    assert not outcome.preferences_created
    assert session.execute.await_count == 2


@pytest.mark.base
@pytest.mark.db
def test_display_name_validation_happens_before_transaction() -> None:
    session = session_with_results()
    repository = DemoUserBootstrapRepository(cast(AsyncSession, session))

    with pytest.raises(ValueError, match="empty"):
        asyncio.run(repository.bootstrap(uuid4(), display_name=" \t "))

    session.begin.assert_not_called()
    assert normalize_display_name("  Demo   User ") == "Demo User"


@pytest.mark.base
@pytest.mark.db
def test_missing_demo_user_id_refuses_before_database_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("database must not be created")

    monkeypatch.setattr(bootstrap_demo_user, "Database", unexpected_database)
    settings = Settings(demo_user_id=None, _env_file=None)

    with pytest.raises(DemoUserConfigurationError, match="demo_user_id_not_configured"):
        asyncio.run(bootstrap_demo_user.run(settings, display_name="Demo User"))


@pytest.mark.base
@pytest.mark.db
def test_missing_configuration_cli_error_is_json_and_contains_no_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bootstrap_demo_user, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("sys.argv", ["bootstrap_demo_user"])

    with pytest.raises(SystemExit) as captured:
        bootstrap_demo_user.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == 2
    assert payload == {"error": "demo_user_id_not_configured", "status": "error"}
    assert "token" not in payload


@pytest.mark.base
@pytest.mark.db
def test_cli_parser_accepts_a_first_creation_display_name() -> None:
    arguments = bootstrap_demo_user.build_parser().parse_args(["--display-name", "Research Demo"])

    assert arguments.display_name == "Research Demo"


@pytest.mark.base
@pytest.mark.db
def test_successful_cli_output_contains_only_safe_bootstrap_fields(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_id = uuid4()

    async def successful_run(
        settings: Settings, *, display_name: str
    ) -> bootstrap_demo_user.DemoUserBootstrapResult:
        del settings
        assert display_name == "Research Demo"
        return bootstrap_demo_user.DemoUserBootstrapResult(
            user_id=user_id,
            user_created=True,
            preferences_created=True,
        )

    monkeypatch.setattr(bootstrap_demo_user, "run", successful_run)
    monkeypatch.setattr(bootstrap_demo_user, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        "sys.argv",
        ["bootstrap_demo_user", "--display-name", "Research Demo"],
    )

    bootstrap_demo_user.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "preferences_created": True,
        "status": "ok",
        "user_created": True,
        "user_id": str(user_id),
    }
    assert "token" not in payload
