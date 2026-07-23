"""Unit tests for behavioral-event persistence primitives."""

import asyncio
from datetime import UTC, datetime
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
def test_event_insert_is_bulk_idempotent_and_counts_returned_ids() -> None:
    async def exercise() -> tuple[int, Insert]:
        session = AsyncMock(spec=AsyncSession)
        scalar_result = MagicMock()
        scalar_result.all.return_value = [uuid4()]
        session.scalars.return_value = scalar_result
        repository = EventRepository(cast(AsyncSession, session))
        events = [_event(), _event()]

        accepted = await repository.insert_events(USER_ID, events)

        statement = cast(Insert, session.scalars.await_args.args[0])
        return accepted, statement

    accepted, statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert accepted == 1
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
        signals = await repository.list_recent_signals(USER_ID, since=NOW)
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
def test_storing_identical_behavior_vector_does_not_touch_preference_row() -> None:
    async def exercise() -> AsyncMock:
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = UserPreference(
            user_id=USER_ID,
            behavior_embedding=[1.0, 0.0],
            behavior_embedding_model="embedding-test-v1",
            model_version=1,
        )
        repository = EventRepository(cast(AsyncSession, session))

        await repository.store_behavior_embedding(
            USER_ID,
            embedding=(1.0, 0.0),
            embedding_model="embedding-test-v1",
            model_version=1,
        )
        return session

    session = asyncio.run(exercise())
    session.flush.assert_not_awaited()
