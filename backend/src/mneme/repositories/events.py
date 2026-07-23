"""Transactional persistence primitives for behavioral events."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, func, select, type_coerce
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from mneme.models.artifact import PaperChunk
from mneme.models.paper import Paper, PaperVersion
from mneme.models.user import EMBEDDING_DIMENSIONS, User, UserEvent, UserEventType, UserPreference
from mneme.services.behavior import BehaviorSignal


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Validated event data ready for idempotent persistence."""

    event_id: UUID
    event_type: UserEventType
    paper_id: UUID | None
    occurred_at: datetime
    duration_ms: int | None
    context: dict[str, object]


class EventRepository:
    """Database operations used by one event-ingestion transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        """Start the single transaction covering ingestion and recomputation."""
        return self._session.begin()

    async def lock_user(self, user_id: UUID) -> bool:
        """Serialize preference writers for one user and verify it exists."""
        locked_id = await self._session.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        return locked_id is not None

    async def existing_event_ids(self, event_ids: set[UUID]) -> set[UUID]:
        """Return globally existing client event IDs without exposing their owners."""
        if not event_ids:
            return set()
        return set(
            (
                await self._session.scalars(select(UserEvent.id).where(UserEvent.id.in_(event_ids)))
            ).all()
        )

    async def existing_paper_ids(self, paper_ids: set[UUID]) -> set[UUID]:
        """Resolve paper IDs referenced by genuinely new events."""
        if not paper_ids:
            return set()
        return set(
            (await self._session.scalars(select(Paper.id).where(Paper.id.in_(paper_ids)))).all()
        )

    async def insert_events(self, user_id: UUID, events: list[EventRecord]) -> int:
        """Insert events once and return the number accepted by PostgreSQL."""
        if not events:
            return 0
        statement = (
            pg_insert(UserEvent)
            .values(
                [
                    {
                        "id": event.event_id,
                        "user_id": user_id,
                        "paper_id": event.paper_id,
                        "event_type": event.event_type,
                        "duration_ms": event.duration_ms,
                        "occurred_at": event.occurred_at,
                        "context": dict(event.context),
                    }
                    for event in events
                ]
            )
            .on_conflict_do_nothing(index_elements=[UserEvent.id])
            .returning(UserEvent.id)
        )
        inserted_ids = list((await self._session.scalars(statement)).all())
        return len(inserted_ids)

    async def list_recent_signals(
        self,
        user_id: UUID,
        *,
        since: datetime,
        until: datetime,
    ) -> list[BehaviorSignal]:
        """Load authoritative raw signals in deterministic order."""
        rows = (
            await self._session.execute(
                select(
                    UserEvent.event_type,
                    UserEvent.paper_id,
                    UserEvent.occurred_at,
                    UserEvent.duration_ms,
                )
                .where(
                    UserEvent.user_id == user_id,
                    UserEvent.occurred_at >= since,
                    UserEvent.occurred_at <= until,
                )
                .order_by(UserEvent.occurred_at, UserEvent.id)
            )
        ).all()
        return [
            BehaviorSignal(
                event_type=event_type,
                paper_id=paper_id,
                occurred_at=occurred_at,
                duration_ms=duration_ms,
            )
            for event_type, paper_id, occurred_at, duration_ms in rows
        ]

    async def mean_latest_embeddings(
        self,
        paper_ids: set[UUID],
        *,
        embedding_model: str,
    ) -> dict[UUID, tuple[float, ...]]:
        """Return mean embeddings from each paper's latest revision and one model."""
        if not paper_ids:
            return {}
        latest_versions = (
            select(
                PaperVersion.paper_id,
                func.max(PaperVersion.version_number).label("version_number"),
            )
            .where(PaperVersion.paper_id.in_(paper_ids))
            .group_by(PaperVersion.paper_id)
            .subquery()
        )
        mean_embedding = type_coerce(
            func.avg(PaperChunk.embedding),
            Vector(EMBEDDING_DIMENSIONS),
        ).label("embedding")
        statement = (
            select(PaperChunk.paper_id, mean_embedding)
            .join(PaperVersion, PaperVersion.id == PaperChunk.paper_version_id)
            .join(
                latest_versions,
                and_(
                    latest_versions.c.paper_id == PaperVersion.paper_id,
                    latest_versions.c.version_number == PaperVersion.version_number,
                ),
            )
            .where(
                PaperChunk.paper_id.in_(paper_ids),
                PaperChunk.embedding.is_not(None),
                PaperChunk.embedding_model == embedding_model,
            )
            .group_by(PaperChunk.paper_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {
            paper_id: tuple(float(value) for value in embedding)
            for paper_id, embedding in rows
            if embedding is not None
        }

    async def lock_preferences(self, user_id: UUID) -> UserPreference:
        """Lock or create the derived-preference row after the user lock."""
        preference = await self._session.scalar(
            select(UserPreference).where(UserPreference.user_id == user_id).with_for_update()
        )
        if preference is None:
            preference = UserPreference(user_id=user_id)
            self._session.add(preference)
            await self._session.flush()
        return preference

    async def store_behavior_embedding(
        self,
        user_id: UUID,
        *,
        embedding: tuple[float, ...] | None,
        embedding_model: str,
        model_version: int,
    ) -> None:
        """Persist a derived vector while preserving explicit preferences."""
        preference = await self.lock_preferences(user_id)
        stored_embedding = list(embedding) if embedding is not None else None
        stored_model = embedding_model if embedding is not None else None
        current_embedding = (
            tuple(float(value) for value in preference.behavior_embedding)
            if preference.behavior_embedding is not None
            else None
        )
        if (
            current_embedding != embedding
            or preference.behavior_embedding_model != stored_model
            or preference.model_version != model_version
        ):
            preference.behavior_embedding = stored_embedding
            preference.behavior_embedding_model = stored_model
            preference.model_version = model_version
            await self._session.flush()
