"""Tests for safe behavior-profile replay from authoritative raw events."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest

from mneme.cli import recompute_behavior
from mneme.core.config import Settings
from mneme.services.behavior_v2 import BehaviorEvidence, BehaviorProfile
from mneme.services.events import EventUserNotFoundError

USER_ID = UUID("00000000-0000-0000-0000-000000000111")


def _profile() -> BehaviorProfile:
    return BehaviorProfile(
        positive_embedding=(1.0, 0.0),
        negative_embedding=None,
        confidence=0.5,
        evidence=BehaviorEvidence(
            signal_count=2,
            eligible_signal_count=1,
            ignored_unexposed_negative_count=1,
            out_of_window_signal_count=0,
            eligible_paper_count=1,
            embedded_paper_count=1,
            positive_paper_count=1,
            negative_paper_count=0,
            positive_support=0.6,
            negative_support=0.0,
            embedding_coverage=1.0,
            parameter_hash="a" * 64,
        ),
    )


@pytest.mark.base
@pytest.mark.db
def test_parser_and_user_resolution_support_explicit_override() -> None:
    explicit = uuid4()
    settings = Settings(demo_user_id=USER_ID, _env_file=None)
    arguments = recompute_behavior.build_parser().parse_args(["--user-id", str(explicit)])

    assert recompute_behavior.resolve_user_id(settings, arguments.user_id) == explicit


@pytest.mark.base
@pytest.mark.db
def test_missing_user_configuration_fails_before_replay() -> None:
    settings = Settings(demo_user_id=None, _env_file=None)

    with pytest.raises(
        recompute_behavior.BehaviorReplayConfigurationError,
        match=recompute_behavior.MISSING_USER_ERROR,
    ):
        recompute_behavior.resolve_user_id(settings, None)


@pytest.mark.base
@pytest.mark.db
def test_run_disposes_database_after_recompute(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile()

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    class FakeDatabase:
        instance: "FakeDatabase | None" = None

        def __init__(self, database_url: str, *, echo: bool) -> None:
            del database_url, echo
            self.disposed = False
            type(self).instance = self

        def session_factory(self) -> FakeSessionContext:
            return FakeSessionContext()

        async def dispose(self) -> None:
            self.disposed = True

    class FakeService:
        def __init__(self, session: object, *, embedding_model: str) -> None:
            del session
            assert embedding_model == "embedding-test-v1"

        async def recompute(self, user_id: UUID) -> BehaviorProfile:
            assert user_id == USER_ID
            return profile

    monkeypatch.setattr(recompute_behavior, "Database", FakeDatabase)
    monkeypatch.setattr(recompute_behavior, "BehaviorEventService", FakeService)
    settings = Settings(
        demo_user_id=USER_ID,
        ai_embedding_model="embedding-test-v1",
        _env_file=None,
    )

    assert asyncio.run(recompute_behavior.run(settings, user_id=USER_ID)) == profile
    assert FakeDatabase.instance is not None
    assert FakeDatabase.instance.disposed


@pytest.mark.base
@pytest.mark.db
def test_success_output_exposes_metadata_but_not_vectors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        demo_user_id=USER_ID,
        ai_embedding_model="embedding-test-v1",
        _env_file=None,
    )

    async def successful_run(settings: Settings, *, user_id: UUID) -> BehaviorProfile:
        del settings
        assert user_id == USER_ID
        return _profile()

    monkeypatch.setattr(recompute_behavior, "get_settings", lambda: settings)
    monkeypatch.setattr(recompute_behavior, "run", successful_run)
    monkeypatch.setattr("sys.argv", ["recompute_behavior"])

    recompute_behavior.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["model_name"] == "behavior-v2"
    assert payload["model_version"] == 2
    assert payload["has_positive_profile"] is True
    assert payload["has_negative_profile"] is False
    assert "embedding" not in payload
    assert "parameter_hash" in payload["evidence"]


@pytest.mark.base
@pytest.mark.db
@pytest.mark.parametrize(
    ("error", "exit_code", "error_code"),
    [
        (EventUserNotFoundError(), 2, recompute_behavior.UNKNOWN_USER_ERROR),
        (ConnectionError("sensitive database detail"), 1, "behavior_replay_unavailable"),
    ],
)
def test_cli_returns_safe_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    error_code: str,
) -> None:
    settings = Settings(demo_user_id=USER_ID, _env_file=None)

    async def failing_run(settings: Settings, *, user_id: UUID) -> BehaviorProfile:
        del settings, user_id
        raise error

    monkeypatch.setattr(recompute_behavior, "get_settings", lambda: settings)
    monkeypatch.setattr(recompute_behavior, "run", failing_run)
    monkeypatch.setattr("sys.argv", ["recompute_behavior"])

    with pytest.raises(SystemExit) as captured:
        recompute_behavior.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == exit_code
    assert payload["error"] == error_code
    assert "sensitive" not in json.dumps(payload)
