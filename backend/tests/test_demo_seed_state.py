"""Unit coverage for persisted demo-seed identity verification."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.schemas.events import UserEvent as UserEventSchema
from mneme.core.config import Settings
from mneme.demo import state
from mneme.demo.manifest import DemoSeedManifest, load_default_demo_seed_manifest
from mneme.demo.seeding_support import DemoSeedError
from mneme.models.user import UserEvent

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PAPER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
SEED_PAPER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ANCHOR = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _event(manifest: DemoSeedManifest) -> UserEventSchema:
    template = manifest.events[0]
    return UserEventSchema(
        event_id=manifest.event_id(template),
        event_type=template.event_type,
        paper_id=PAPER_ID,
        occurred_at=manifest.event_time(template, ANCHOR),
        duration_ms=template.duration_ms,
        context={
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest.content_sha256(),
            "source": "demo_seed",
        },
    )


class FakeSession:
    def __init__(self, seed_paper_id: UUID | None, events: list[UserEvent]) -> None:
        self.seed_paper_id = seed_paper_id
        self.events = events

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def scalar(self, _statement: object) -> UUID | None:
        return self.seed_paper_id

    async def scalars(self, _statement: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.events)


class FakeDatabase:
    def __init__(self, session: FakeSession) -> None:
        self.session_factory: Callable[[], AsyncSession] = cast(
            Callable[[], AsyncSession], lambda: session
        )
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def _stored_event(expected: UserEventSchema) -> UserEvent:
    return UserEvent(
        id=expected.event_id,
        user_id=USER_ID,
        event_type=expected.event_type,
        paper_id=expected.paper_id,
        occurred_at=expected.occurred_at,
        duration_ms=expected.duration_ms,
        context=dict(expected.context),
    )


def _verify_with(
    monkeypatch: pytest.MonkeyPatch,
    *,
    seed_paper_id: UUID | None,
    stored_events: list[UserEvent],
) -> tuple[UUID, FakeDatabase]:
    database = FakeDatabase(FakeSession(seed_paper_id, stored_events))
    monkeypatch.setattr(state.Database, "from_settings", lambda *_args, **_kwargs: database)
    manifest = load_default_demo_seed_manifest()
    event = _event(manifest)
    result = asyncio.run(
        state.verify_persisted_seed_state(
            Settings(demo_user_id=USER_ID, _env_file=None), manifest, [event]
        )
    )
    return result, database


@pytest.mark.base
@pytest.mark.db
def test_persisted_demo_seed_state_returns_stable_paper_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_default_demo_seed_manifest()
    result, database = _verify_with(
        monkeypatch,
        seed_paper_id=SEED_PAPER_ID,
        stored_events=[_stored_event(_event(manifest))],
    )

    assert result == SEED_PAPER_ID
    assert database.disposed


@pytest.mark.base
@pytest.mark.db
def test_persisted_demo_seed_state_rejects_manifest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_default_demo_seed_manifest()
    stored = _stored_event(_event(manifest))
    stored.context = {**stored.context, "manifest_sha256": "0" * 64}
    database = FakeDatabase(FakeSession(SEED_PAPER_ID, [stored]))
    monkeypatch.setattr(state.Database, "from_settings", lambda *_args, **_kwargs: database)

    with pytest.raises(DemoSeedError, match="do not match"):
        asyncio.run(
            state.verify_persisted_seed_state(
                Settings(demo_user_id=USER_ID, _env_file=None),
                manifest,
                [_event(manifest)],
            )
        )
    assert database.disposed


@pytest.mark.base
@pytest.mark.db
@pytest.mark.parametrize("seed_paper_id,events", [(None, [object()]), (SEED_PAPER_ID, [])])
def test_persisted_demo_seed_state_rejects_missing_rows(
    monkeypatch: pytest.MonkeyPatch,
    seed_paper_id: UUID | None,
    events: list[object],
) -> None:
    database = FakeDatabase(FakeSession(seed_paper_id, cast(list[UserEvent], events)))
    monkeypatch.setattr(state.Database, "from_settings", lambda *_args, **_kwargs: database)
    manifest = load_default_demo_seed_manifest()

    with pytest.raises(DemoSeedError):
        asyncio.run(
            state.verify_persisted_seed_state(
                Settings(demo_user_id=USER_ID, _env_file=None),
                manifest,
                [_event(manifest)],
            )
        )
    assert database.disposed
