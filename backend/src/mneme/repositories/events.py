"""Transactional persistence primitives for behavioral events."""

import struct
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, func, select, type_coerce, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from sqlalchemy.orm.attributes import set_committed_value

from mneme.models.artifact import PaperChunk
from mneme.models.paper import Paper, PaperVersion
from mneme.models.user import EMBEDDING_DIMENSIONS, User, UserEvent, UserEventType, UserPreference
from mneme.services.behavior import BehaviorSignal
from mneme.services.behavior_v2 import BehaviorProfile


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

    async def insert_events(self, user_id: UUID, events: list[EventRecord]) -> set[UUID]:
        """Insert events once and return the IDs accepted by PostgreSQL."""
        if not events:
            return set()
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
        return set((await self._session.scalars(statement)).all())

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

    async def store_behavior_profile(
        self,
        user_id: UUID,
        *,
        profile: BehaviorProfile,
        embedding_model: str,
        advance_freshness: bool = True,
    ) -> None:
        """Persist a derived profile and advance freshness only for ranking changes."""
        preference = await self.lock_preferences(user_id)
        positive = _as_pgvector_tuple(profile.positive_embedding)
        negative = _as_pgvector_tuple(profile.negative_embedding)
        stored_model = embedding_model if positive is not None or negative is not None else None
        current_positive = _as_float_tuple(preference.behavior_embedding)
        current_negative = _as_float_tuple(preference.negative_behavior_embedding)
        evidence: dict[str, object] = {
            "model_name": profile.model_name,
            "model_version": profile.model_version,
            **profile.evidence.as_json(),
        }
        ranking_state_changed = (
            current_positive != positive
            or current_negative != negative
            or preference.behavior_embedding_model != stored_model
            or preference.behavior_confidence != profile.confidence
            or preference.model_version != profile.model_version
        )
        identity_changed = (
            preference.behavior_embedding_model != stored_model
            or preference.model_version != profile.model_version
        )
        evidence_changed = preference.behavior_evidence != evidence
        if ranking_state_changed and (advance_freshness or identity_changed):
            preference.behavior_embedding = list(positive) if positive is not None else None
            preference.negative_behavior_embedding = (
                list(negative) if negative is not None else None
            )
            preference.behavior_embedding_model = stored_model
            preference.behavior_confidence = profile.confidence
            preference.behavior_evidence = evidence
            preference.model_version = profile.model_version
            await self._session.flush()
        elif ranking_state_changed or evidence_changed:
            # Keep the complete derived snapshot inspectable without expiring a digest when
            # the newly accepted batch has no effect on recommendation semantics.
            stored_positive = list(positive) if positive is not None else None
            stored_negative = list(negative) if negative is not None else None
            await self._session.execute(
                update(UserPreference)
                .where(UserPreference.user_id == user_id)
                .values(
                    behavior_embedding=stored_positive,
                    negative_behavior_embedding=stored_negative,
                    behavior_embedding_model=stored_model,
                    behavior_confidence=profile.confidence,
                    behavior_evidence=evidence,
                    model_version=profile.model_version,
                    updated_at=preference.updated_at,
                )
                .execution_options(synchronize_session=False)
            )
            set_committed_value(preference, "behavior_embedding", stored_positive)
            set_committed_value(preference, "negative_behavior_embedding", stored_negative)
            set_committed_value(preference, "behavior_embedding_model", stored_model)
            set_committed_value(preference, "behavior_confidence", profile.confidence)
            set_committed_value(preference, "behavior_evidence", evidence)
            set_committed_value(preference, "model_version", profile.model_version)


def _as_float_tuple(value: list[float] | None) -> tuple[float, ...] | None:
    if value is None:
        return None
    return tuple(float(item) for item in value)


def _as_pgvector_tuple(
    value: tuple[float, ...] | None,
) -> tuple[float, ...] | None:
    """Match pgvector's single-precision storage before no-op comparison."""
    if value is None:
        return None
    return tuple(struct.unpack("!f", struct.pack("!f", float(item)))[0] for item in value)
