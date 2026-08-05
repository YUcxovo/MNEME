"""Atomic behavioral-event ingestion and preference recomputation."""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.repositories.events import EventRecord, EventRepository
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2 import (
    BEHAVIOR_MODEL_NAME,
    DEFAULT_BEHAVIOR_CONFIG,
    BehaviorProfile,
)
from mneme.services.behavior_v2_profile import aggregate_behavior_profile

logger = structlog.get_logger(__name__)

EVENT_MAX_FUTURE_SKEW = timedelta(minutes=5)


class EventUserNotFoundError(LookupError):
    """Raised when the authenticated demo user was not bootstrapped."""


class EventPaperNotFoundError(LookupError):
    """Raised when a new event references an unknown paper."""


class EventTimestampOutOfRangeError(ValueError):
    """Raised when an event is too far ahead of the server clock."""


@dataclass(frozen=True, slots=True)
class EventIngestionStats:
    """Idempotent batch ingestion counts."""

    accepted: int
    duplicates: int


class BehaviorEventService:
    """Persist one batch and rebuild behavior-v2 in a single transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_model: str,
        repository: EventRepository | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository or EventRepository(session)
        self._embedding_model = embedding_model
        self._clock = clock

    async def ingest(
        self,
        user_id: UUID,
        events: Sequence[EventRecord],
    ) -> EventIngestionStats:
        """Ingest events once and atomically refresh the derived preference."""
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Event ingestion clock must be timezone-aware.")
        if any(event.occurred_at.tzinfo is None for event in events):
            raise ValueError("Event timestamps must be timezone-aware.")
        latest_allowed = now + EVENT_MAX_FUTURE_SKEW
        if any(event.occurred_at > latest_allowed for event in events):
            raise EventTimestampOutOfRangeError

        async with self._repository.transaction():
            if not await self._repository.lock_user(user_id):
                raise EventUserNotFoundError

            existing_ids = await self._repository.existing_event_ids(
                {event.event_id for event in events}
            )
            new_by_id: dict[UUID, EventRecord] = {}
            for event in events:
                if event.event_id not in existing_ids:
                    new_by_id.setdefault(event.event_id, event)
            new_events = list(new_by_id.values())

            referenced_papers = {
                event.paper_id for event in new_events if event.paper_id is not None
            }
            known_papers = await self._repository.existing_paper_ids(referenced_papers)
            if referenced_papers - known_papers:
                raise EventPaperNotFoundError

            inserted_ids = await self._repository.insert_events(user_id, new_events)
            accepted_events = [event for event in new_events if event.event_id in inserted_ids]
            profile = await self._recompute_locked(
                user_id,
                now=now,
                latest_allowed=latest_allowed,
                accepted_events=accepted_events,
            )

        result = EventIngestionStats(
            accepted=len(inserted_ids),
            duplicates=len(events) - len(inserted_ids),
        )
        logger.info(
            "behavior_events_ingested",
            user_id=str(user_id),
            accepted=result.accepted,
            duplicates=result.duplicates,
            behavior_model=BEHAVIOR_MODEL_NAME,
            behavior_profile=(
                profile.positive_embedding is not None or profile.negative_embedding is not None
            ),
            behavior_confidence=profile.confidence,
        )
        return result

    async def recompute(self, user_id: UUID) -> BehaviorProfile:
        """Rebuild one active profile from raw events without inserting an event batch."""
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Event ingestion clock must be timezone-aware.")
        latest_allowed = now + EVENT_MAX_FUTURE_SKEW
        async with self._repository.transaction():
            if not await self._repository.lock_user(user_id):
                raise EventUserNotFoundError
            profile = await self._recompute_locked(user_id, now=now, latest_allowed=latest_allowed)
        logger.info(
            "behavior_profile_recomputed",
            user_id=str(user_id),
            behavior_model=BEHAVIOR_MODEL_NAME,
            behavior_confidence=profile.confidence,
            eligible_signals=profile.evidence.eligible_signal_count,
        )
        return profile

    async def _recompute_locked(
        self,
        user_id: UUID,
        *,
        now: datetime,
        latest_allowed: datetime,
        accepted_events: Sequence[EventRecord] | None = None,
    ) -> BehaviorProfile:
        signals = await self._repository.list_recent_signals(
            user_id,
            since=now - timedelta(days=DEFAULT_BEHAVIOR_CONFIG.window_days),
            until=latest_allowed,
        )
        signal_papers = {signal.paper_id for signal in signals if signal.paper_id is not None}
        embeddings = await self._repository.mean_latest_embeddings(
            signal_papers,
            embedding_model=self._embedding_model,
        )
        profile = aggregate_behavior_profile(signals, embeddings, now=now)
        advance_freshness = True
        if accepted_events is not None:
            prior_profile = aggregate_behavior_profile(
                _without_events(signals, accepted_events),
                embeddings,
                now=now,
            )
            advance_freshness = not _same_recommendation_profile(prior_profile, profile)
        await self._repository.store_behavior_profile(
            user_id,
            profile=profile,
            embedding_model=self._embedding_model,
            advance_freshness=advance_freshness,
        )
        return profile


def _without_events(
    signals: Sequence[BehaviorSignal],
    events: Sequence[EventRecord],
) -> list[BehaviorSignal]:
    """Remove the exactly accepted event multiset from a loaded signal history."""
    accepted = Counter(
        (event.event_type, event.paper_id, event.occurred_at, event.duration_ms) for event in events
    )
    prior: list[BehaviorSignal] = []
    for signal in signals:
        key = (signal.event_type, signal.paper_id, signal.occurred_at, signal.duration_ms)
        if accepted[key] > 0:
            accepted[key] -= 1
        else:
            prior.append(signal)
    return prior


def _same_recommendation_profile(left: BehaviorProfile, right: BehaviorProfile) -> bool:
    """Compare only profile fields consumed by recommendation scoring."""
    return (
        left.positive_embedding == right.positive_embedding
        and left.negative_embedding == right.negative_embedding
        and left.confidence == right.confidence
        and left.model_version == right.model_version
    )
