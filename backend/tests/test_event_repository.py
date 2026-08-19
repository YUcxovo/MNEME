"""Unit tests for behavioral-event persistence primitives."""

import asyncio
import struct
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from mneme.models.user import UserEventType, UserPreference
from mneme.repositories.events import EventRecord, EventRepository
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2_profile import aggregate_behavior_profile

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _event(event_id: UUID | None = None) -> EventRecord:
    return EventRecord(
        event_id=event_id or uuid4(),
        event_type=UserEventType.PAPER_SAVED,
        paper_id=PAPER_ID,
        occurred_at=NOW,
        duration_ms=None,
        context={"surface": "digest"},
    )


@pytest.mark.base
@pytest.mark.db
def test_event_insert_is_bulk_idempotent_and_returns_accepted_ids() -> None:
    async def exercise() -> tuple[set[UUID], Insert]:
        session = AsyncMock(spec=AsyncSession)
        scalar_result = MagicMock()
        scalar_result.all.return_value = [uuid4()]
        session.scalars.return_value = scalar_result
        repository = EventRepository(cast(AsyncSession, session))
        events = [_event(), _event()]

        accepted_ids = await repository.insert_events(USER_ID, events)

        statement = cast(Insert, session.scalars.await_args.args[0])
        return accepted_ids, statement

    accepted_ids, statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert len(accepted_ids) == 1
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert "RETURNING user_events.id" in sql
    assert compiled.params["user_id_m0"] == USER_ID
    assert compiled.params["event_type_m0"] == UserEventType.PAPER_SAVED
    assert compiled.params["context_m0"] == {"surface": "digest"}


@pytest.mark.base
@pytest.mark.db
def test_user_lock_and_signal_history_queries_preserve_transaction_ordering() -> None:
    async def exercise() -> tuple[ClauseElement, ClauseElement]:
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = USER_ID
        rows = MagicMock()
        rows.all.return_value = [
            (UserEventType.PAPER_OPENED, PAPER_ID, NOW, 45_000),
        ]
        session.execute.return_value = rows
        repository = EventRepository(cast(AsyncSession, session))

        assert await repository.lock_user(USER_ID)
        signals = await repository.list_recent_signals(USER_ID, since=NOW, until=NOW)
        assert signals[0].duration_ms == 45_000
        return (
            cast(ClauseElement, session.scalar.await_args.args[0]),
            cast(ClauseElement, session.execute.await_args.args[0]),
        )

    lock_statement, history_statement = asyncio.run(exercise())
    lock_sql = str(lock_statement.compile(dialect=postgresql.dialect()))
    history_sql = str(history_statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in lock_sql
    assert "user_events.occurred_at >=" in history_sql
    assert "user_events.occurred_at <=" in history_sql
    assert "ORDER BY user_events.occurred_at, user_events.id" in history_sql


@pytest.mark.base
@pytest.mark.db
def test_embedding_query_uses_latest_revision_and_exact_model() -> None:
    async def exercise() -> tuple[dict[UUID, tuple[float, ...]], ClauseElement]:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.all.return_value = [(PAPER_ID, [0.25, 0.75])]
        session.execute.return_value = result
        repository = EventRepository(cast(AsyncSession, session))

        embeddings = await repository.mean_latest_embeddings(
            {PAPER_ID},
            embedding_model="embedding-test-v1",
        )
        return embeddings, cast(ClauseElement, session.execute.await_args.args[0])

    embeddings, statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert embeddings == {PAPER_ID: (0.25, 0.75)}
    assert "max(paper_versions.version_number)" in sql
    assert "paper_chunks.embedding_model =" in sql
    assert compiled.params is not None
    assert "embedding-test-v1" in compiled.params.values()


@pytest.mark.base
@pytest.mark.db
def test_storing_identical_behavior_profile_does_not_touch_preference_row() -> None:
    async def exercise() -> AsyncMock:
        profile = aggregate_behavior_profile(
            [BehaviorSignal(UserEventType.PAPER_SAVED, PAPER_ID, NOW)],
            {PAPER_ID: (1.0, 0.0)},
            now=NOW,
        )
        evidence = {
            "model_name": profile.model_name,
            "model_version": profile.model_version,
            **profile.evidence.as_json(),
        }
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = UserPreference(
            user_id=USER_ID,
            behavior_embedding=[1.0, 0.0],
            negative_behavior_embedding=None,
            behavior_embedding_model="embedding-test-v1",
            behavior_confidence=profile.confidence,
            behavior_evidence=evidence,
            model_version=profile.model_version,
        )
        repository = EventRepository(cast(AsyncSession, session))

        await repository.store_behavior_profile(
            USER_ID,
            profile=profile,
            embedding_model="embedding-test-v1",
        )
        return session

    session = asyncio.run(exercise())
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.base
@pytest.mark.db
def test_evidence_only_profile_change_preserves_digest_freshness_timestamp() -> None:
    async def exercise() -> tuple[AsyncMock, UserPreference, ClauseElement]:
        previous = aggregate_behavior_profile([], {}, now=NOW)
        current = aggregate_behavior_profile(
            [BehaviorSignal(UserEventType.PAPER_IMPRESSION, PAPER_ID, NOW)],
            {},
            now=NOW,
        )
        assert previous.evidence.signal_count == 0
        assert current.evidence.signal_count == 1
        assert current.positive_embedding == previous.positive_embedding
        assert current.negative_embedding == previous.negative_embedding
        assert current.confidence == previous.confidence

        evidence = {
            "model_name": previous.model_name,
            "model_version": previous.model_version,
            **previous.evidence.as_json(),
        }
        session = AsyncMock(spec=AsyncSession)
        preference = UserPreference(
            user_id=USER_ID,
            behavior_embedding=None,
            negative_behavior_embedding=None,
            behavior_embedding_model=None,
            behavior_confidence=previous.confidence,
            behavior_evidence=evidence,
            model_version=previous.model_version,
            updated_at=NOW,
        )
        session.scalar.return_value = preference

        await EventRepository(cast(AsyncSession, session)).store_behavior_profile(
            USER_ID,
            profile=current,
            embedding_model="embedding-test-v1",
        )

        await_args = session.execute.await_args
        assert await_args is not None
        return session, preference, cast(ClauseElement, await_args.args[0])

    session, preference, statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "UPDATE user_preferences" in str(compiled)
    assert compiled.params is not None
    assert compiled.params["updated_at"] == NOW
    assert preference.updated_at == NOW
    assert preference.behavior_evidence["signal_count"] == 1
    session.flush.assert_not_awaited()


@pytest.mark.base
@pytest.mark.db
def test_non_advancing_recompute_persists_decay_without_expiring_digest() -> None:
    async def exercise() -> tuple[UserPreference, ClauseElement, float]:
        signal = BehaviorSignal(
            UserEventType.PAPER_SAVED,
            PAPER_ID,
            NOW - timedelta(hours=1),
        )
        previous = aggregate_behavior_profile(
            [signal],
            {PAPER_ID: (1.0, 0.0)},
            now=NOW - timedelta(minutes=30),
        )
        current = aggregate_behavior_profile(
            [signal, BehaviorSignal(UserEventType.PAPER_IMPRESSION, PAPER_ID, NOW)],
            {PAPER_ID: (1.0, 0.0)},
            now=NOW,
        )
        assert current.confidence != previous.confidence
        evidence = {
            "model_name": previous.model_name,
            "model_version": previous.model_version,
            **previous.evidence.as_json(),
        }
        session = AsyncMock(spec=AsyncSession)
        preference = UserPreference(
            user_id=USER_ID,
            behavior_embedding=list(previous.positive_embedding or ()),
            negative_behavior_embedding=None,
            behavior_embedding_model="embedding-test-v1",
            behavior_confidence=previous.confidence,
            behavior_evidence=evidence,
            model_version=previous.model_version,
            updated_at=NOW,
        )
        session.scalar.return_value = preference

        await EventRepository(cast(AsyncSession, session)).store_behavior_profile(
            USER_ID,
            profile=current,
            embedding_model="embedding-test-v1",
            advance_freshness=False,
        )

        await_args = session.execute.await_args
        assert await_args is not None
        return preference, cast(ClauseElement, await_args.args[0]), current.confidence

    preference, statement, current_confidence = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params is not None
    assert compiled.params["updated_at"] == NOW
    assert preference.updated_at == NOW
    assert preference.behavior_confidence == current_confidence


@pytest.mark.base
@pytest.mark.db
def test_embedding_model_change_always_advances_recommendation_freshness() -> None:
    async def exercise() -> AsyncMock:
        profile = aggregate_behavior_profile(
            [BehaviorSignal(UserEventType.PAPER_SAVED, PAPER_ID, NOW)],
            {PAPER_ID: (1.0, 0.0)},
            now=NOW,
        )
        evidence = {
            "model_name": profile.model_name,
            "model_version": profile.model_version,
            **profile.evidence.as_json(),
        }
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = UserPreference(
            user_id=USER_ID,
            behavior_embedding=list(profile.positive_embedding or ()),
            negative_behavior_embedding=None,
            behavior_embedding_model="embedding-old-v1",
            behavior_confidence=profile.confidence,
            behavior_evidence=evidence,
            model_version=profile.model_version,
            updated_at=NOW,
        )

        await EventRepository(cast(AsyncSession, session)).store_behavior_profile(
            USER_ID,
            profile=profile,
            embedding_model="embedding-new-v2",
            advance_freshness=False,
        )
        return session

    session = asyncio.run(exercise())
    session.execute.assert_not_awaited()
    session.flush.assert_awaited_once()


@pytest.mark.base
@pytest.mark.db
def test_pgvector_float32_round_trip_remains_a_profile_noop() -> None:
    async def exercise() -> AsyncMock:
        profile = aggregate_behavior_profile(
            [BehaviorSignal(UserEventType.PAPER_SAVED, PAPER_ID, NOW)],
            {PAPER_ID: (0.9606839529674632, 0.2776432713320825)},
            now=NOW,
        )
        assert profile.positive_embedding is not None
        stored_vector = [
            struct.unpack("!f", struct.pack("!f", value))[0] for value in profile.positive_embedding
        ]
        evidence = {
            "model_name": profile.model_name,
            "model_version": profile.model_version,
            **profile.evidence.as_json(),
        }
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = UserPreference(
            user_id=USER_ID,
            behavior_embedding=stored_vector,
            negative_behavior_embedding=None,
            behavior_embedding_model="embedding-test-v1",
            behavior_confidence=profile.confidence,
            behavior_evidence=evidence,
            model_version=profile.model_version,
        )

        await EventRepository(cast(AsyncSession, session)).store_behavior_profile(
            USER_ID,
            profile=replace(profile),
            embedding_model="embedding-test-v1",
        )
        return session

    session = asyncio.run(exercise())
    session.flush.assert_not_awaited()
