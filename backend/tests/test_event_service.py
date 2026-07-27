"""Tests for atomic event ingestion and behavior recomputation."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.user import UserEventType
from mneme.repositories.events import EventRecord, EventRepository
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2 import (
    BEHAVIOR_MODEL_VERSION,
    DEFAULT_BEHAVIOR_CONFIG,
    BehaviorProfile,
)
from mneme.services.events import (
    BehaviorEventService,
    EventPaperNotFoundError,
    EventTimestampOutOfRangeError,
    EventUserNotFoundError,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


class FakeTransaction:
    def __init__(self) -> None:
        self.entered = False
        self.exception_type: type[BaseException] | None = None

    async def __aenter__(self) -> "FakeTransaction":
        self.entered = True
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.exception_type = exception_type


class FakeEventRepository:
    def __init__(self) -> None:
        self.user_exists = True
        self.existing_ids: set[UUID] = set()
        self.known_papers = {PAPER_ID}
        self.signals: list[BehaviorSignal] = []
        self.embeddings: dict[UUID, tuple[float, ...]] = {}
        self.transaction_state = FakeTransaction()
        self.inserted: list[EventRecord] = []
        self.signal_since: datetime | None = None
        self.signal_until: datetime | None = None
        self.embedding_model: str | None = None
        self.stored: tuple[UUID, BehaviorProfile, str] | None = None

    def transaction(self) -> FakeTransaction:
        return self.transaction_state

    async def lock_user(self, user_id: UUID) -> bool:
        assert user_id == USER_ID
        return self.user_exists

    async def existing_event_ids(self, _event_ids: set[UUID]) -> set[UUID]:
        return self.existing_ids

    async def existing_paper_ids(self, _paper_ids: set[UUID]) -> set[UUID]:
        return self.known_papers

    async def insert_events(self, user_id: UUID, events: list[EventRecord]) -> int:
        assert user_id == USER_ID
        self.inserted = events
        return len(events)

    async def list_recent_signals(
        self, user_id: UUID, *, since: datetime, until: datetime
    ) -> list[BehaviorSignal]:
        assert user_id == USER_ID
        self.signal_since = since
        self.signal_until = until
        return self.signals

    async def mean_latest_embeddings(
        self, _paper_ids: set[UUID], *, embedding_model: str
    ) -> dict[UUID, tuple[float, ...]]:
        self.embedding_model = embedding_model
        return self.embeddings

    async def store_behavior_profile(
        self,
        user_id: UUID,
        *,
        profile: BehaviorProfile,
        embedding_model: str,
    ) -> None:
        self.stored = (user_id, profile, embedding_model)


def _event(event_id: UUID, *, paper_id: UUID = PAPER_ID) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        event_type=UserEventType.PAPER_SAVED,
        paper_id=paper_id,
        occurred_at=NOW,
        duration_ms=None,
        context={},
    )


def _service(repository: FakeEventRepository) -> BehaviorEventService:
    return BehaviorEventService(
        cast(AsyncSession, MagicMock()),
        embedding_model="embedding-test-v1",
        repository=cast(EventRepository, repository),
        clock=lambda: NOW,
    )


@pytest.mark.base
@pytest.mark.db
def test_event_service_deduplicates_and_recomputes_in_one_transaction() -> None:
    repository = FakeEventRepository()
    existing_id = uuid4()
    new_id = uuid4()
    repository.existing_ids = {existing_id}
    repository.signals = [
        BehaviorSignal(UserEventType.PAPER_SAVED, PAPER_ID, NOW),
    ]
    repository.embeddings = {PAPER_ID: (1.0, 0.0)}

    result = asyncio.run(
        _service(repository).ingest(
            USER_ID,
            [_event(existing_id), _event(new_id), _event(new_id)],
        )
    )

    assert result.accepted == 1
    assert result.duplicates == 2
    assert [event.event_id for event in repository.inserted] == [new_id]
    assert repository.transaction_state.entered
    assert repository.transaction_state.exception_type is None
    assert repository.signal_since == NOW - timedelta(days=DEFAULT_BEHAVIOR_CONFIG.window_days)
    assert repository.signal_until == NOW + timedelta(minutes=5)
    assert repository.embedding_model == "embedding-test-v1"
    assert repository.stored is not None
    stored_user, profile, stored_model = repository.stored
    assert stored_user == USER_ID
    assert profile.positive_embedding == pytest.approx((1.0, 0.0))
    assert profile.negative_embedding is None
    assert profile.model_version == BEHAVIOR_MODEL_VERSION
    assert 0 < profile.confidence < 1
    assert stored_model == "embedding-test-v1"


@pytest.mark.base
@pytest.mark.db
def test_unknown_paper_aborts_the_entire_batch() -> None:
    repository = FakeEventRepository()
    repository.known_papers = set()

    with pytest.raises(EventPaperNotFoundError):
        asyncio.run(_service(repository).ingest(USER_ID, [_event(uuid4())]))

    assert repository.inserted == []
    assert repository.stored is None
    assert repository.transaction_state.exception_type is EventPaperNotFoundError


@pytest.mark.base
@pytest.mark.db
def test_missing_user_aborts_before_event_queries() -> None:
    repository = FakeEventRepository()
    repository.user_exists = False

    with pytest.raises(EventUserNotFoundError):
        asyncio.run(_service(repository).ingest(USER_ID, [_event(uuid4())]))

    assert repository.inserted == []
    assert repository.transaction_state.exception_type is EventUserNotFoundError


@pytest.mark.base
@pytest.mark.db
def test_empty_batch_can_deterministically_clear_stale_behavior() -> None:
    repository = FakeEventRepository()

    result = asyncio.run(_service(repository).ingest(USER_ID, []))

    assert result.accepted == 0
    assert result.duplicates == 0
    assert repository.stored is not None
    stored_user, profile, stored_model = repository.stored
    assert stored_user == USER_ID
    assert profile.positive_embedding is None
    assert profile.negative_embedding is None
    assert profile.model_version == BEHAVIOR_MODEL_VERSION
    assert profile.confidence == 0
    assert stored_model == "embedding-test-v1"


@pytest.mark.base
@pytest.mark.db
def test_recompute_replays_raw_history_without_inserting_events() -> None:
    repository = FakeEventRepository()
    repository.signals = [
        BehaviorSignal(UserEventType.PAPER_SAVED, PAPER_ID, NOW),
    ]
    repository.embeddings = {PAPER_ID: (0.0, 1.0)}

    profile = asyncio.run(_service(repository).recompute(USER_ID))

    assert repository.inserted == []
    assert repository.transaction_state.entered
    assert repository.transaction_state.exception_type is None
    assert profile.positive_embedding == pytest.approx((0.0, 1.0))
    assert repository.stored == (USER_ID, profile, "embedding-test-v1")


@pytest.mark.base
@pytest.mark.db
def test_event_service_rejects_timestamps_beyond_clock_skew() -> None:
    repository = FakeEventRepository()
    event = _event(uuid4())
    future_event = EventRecord(
        event_id=event.event_id,
        event_type=event.event_type,
        paper_id=event.paper_id,
        occurred_at=NOW + timedelta(minutes=5, microseconds=1),
        duration_ms=event.duration_ms,
        context=event.context,
    )

    with pytest.raises(EventTimestampOutOfRangeError):
        asyncio.run(_service(repository).ingest(USER_ID, [future_event]))

    assert not repository.transaction_state.entered
