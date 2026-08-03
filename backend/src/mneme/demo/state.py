"""Database verification for one persisted demo seed run."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from mneme.api.schemas.events import UserEvent as UserEventSchema
from mneme.core.config import Settings
from mneme.db.session import Database
from mneme.demo.manifest import DemoSeedManifest
from mneme.demo.seeding_support import DemoSeedConfigurationError, DemoSeedError
from mneme.models.paper import Paper, ProcessingStatus
from mneme.models.user import UserEvent


async def verify_persisted_seed_state(
    settings: Settings,
    manifest: DemoSeedManifest,
    events: list[UserEventSchema],
) -> UUID:
    """Verify event identity and content, then return the stable seed paper ID."""
    if settings.demo_user_id is None:
        raise DemoSeedConfigurationError("Demo user ID is not configured")
    expected_events = {event.event_id: event for event in events}
    database = Database.from_settings(settings, echo=False)
    query_succeeded = False
    try:
        async with database.session_factory() as session:
            seed_paper_id = await session.scalar(
                select(Paper.id)
                .where(
                    Paper.arxiv_id == manifest.seed_arxiv_reference,
                    Paper.processing_status == ProcessingStatus.READY,
                )
                .limit(1)
            )
            stored_events = list(
                (
                    await session.scalars(
                        select(UserEvent).where(UserEvent.id.in_(set(expected_events)))
                    )
                ).all()
            )
        query_succeeded = True
    except (OSError, SQLAlchemyError) as exception:
        raise DemoSeedError("Persisted demo state verification failed") from exception
    finally:
        try:
            await database.dispose()
        except (OSError, SQLAlchemyError) as exception:
            if query_succeeded:
                raise DemoSeedError("Demo state verifier did not close cleanly") from exception
    if seed_paper_id is None:
        raise DemoSeedError("The persisted seed paper is unavailable")
    if len(stored_events) != len(expected_events):
        raise DemoSeedError("The persisted demo event set is incomplete")
    for stored in stored_events:
        expected = expected_events.get(stored.id)
        if expected is None or not _event_matches(stored, expected, settings.demo_user_id):
            raise DemoSeedError("Persisted demo events do not match the manifest")
    return seed_paper_id


def _event_matches(stored: UserEvent, expected: UserEventSchema, user_id: UUID) -> bool:
    return (
        stored.user_id == user_id
        and stored.event_type == expected.event_type
        and stored.paper_id == expected.paper_id
        and stored.occurred_at == expected.occurred_at
        and stored.duration_ms == expected.duration_ms
        and stored.context == expected.context
    )
