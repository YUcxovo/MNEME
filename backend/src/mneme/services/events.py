"""Atomic behavioral-event ingestion and preference recomputation."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.repositories.events import EventRecord, EventRepository
from mneme.services.behavior import (
    BEHAVIOR_MODEL_VERSION,
    BEHAVIOR_WINDOW_DAYS,
    aggregate_behavior_embedding,
)

logger = structlog.get_logger(__name__)


class EventUserNotFoundError(LookupError):
    """Raised when the authenticated demo user was not bootstrapped."""


class EventPaperNotFoundError(LookupError):
    """Raised when a new event references an unknown paper."""


@dataclass(frozen=True, slots=True)
class EventIngestionStats:
    """Idempotent batch ingestion counts."""

    accepted: int
    duplicates: int


class BehaviorEventService:
    """Persist one batch and rebuild behavior-v1 in a single transaction."""

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

            accepted = await self._repository.insert_events(user_id, new_events)
            signals = await self._repository.list_recent_signals(
                user_id,
                since=now - timedelta(days=BEHAVIOR_WINDOW_DAYS),
            )
            signal_papers = {signal.paper_id for signal in signals if signal.paper_id is not None}
            embeddings = await self._repository.mean_latest_embeddings(
                signal_papers,
                embedding_model=self._embedding_model,
            )
            behavior_embedding = aggregate_behavior_embedding(
                signals,
                embeddings,
                now=now,
            )
            await self._repository.store_behavior_embedding(
                user_id,
                embedding=behavior_embedding,
                embedding_model=self._embedding_model,
                model_version=BEHAVIOR_MODEL_VERSION,
            )

        result = EventIngestionStats(
            accepted=accepted,
            duplicates=len(events) - accepted,
        )
        logger.info(
            "behavior_events_ingested",
            user_id=str(user_id),
            accepted=result.accepted,
            duplicates=result.duplicates,
            behavior_vector=behavior_embedding is not None,
        )
        return result
