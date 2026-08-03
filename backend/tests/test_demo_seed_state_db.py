"""PostgreSQL proof for idempotent demo events and persisted-state drift checks."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, update

from mneme.api.schemas.events import UserEvent as UserEventSchema
from mneme.core.config import Settings
from mneme.db.session import Database
from mneme.demo.manifest import load_default_demo_seed_manifest
from mneme.demo.seeding_support import DemoSeedError
from mneme.demo.state import verify_persisted_seed_state
from mneme.models.paper import Paper, ProcessingStatus
from mneme.models.user import User, UserEvent
from mneme.repositories.events import EventRepository

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.db, pytest.mark.pipeline]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


def _paper(paper_id: UUID, arxiv_id: str, rank: int) -> Paper:
    now = datetime.now(UTC)
    return Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        title=f"Demo state paper {rank}",
        abstract="Database fixture for deterministic demo state verification.",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        processing_status=ProcessingStatus.READY,
        published_at=now,
        source_updated_at=now,
    )


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    seed_paper_id = uuid4()
    digest_paper_ids = tuple(uuid4() for _ in range(5))
    seed_arxiv_id = f"m5/{int(suffix[:8], 16) % 10_000_000:07d}"
    manifest = load_default_demo_seed_manifest().model_copy(
        update={
            "manifest_id": f"mneme-m5-{suffix}",
            "seed_arxiv_reference": seed_arxiv_id,
        }
    )
    anchor = datetime(2026, 8, 3, 12, tzinfo=UTC)
    manifest_hash = manifest.content_sha256()
    events = [
        UserEventSchema(
            event_id=manifest.event_id(template),
            event_type=template.event_type,
            paper_id=digest_paper_ids[template.paper_rank - 1],
            occurred_at=manifest.event_time(template, anchor),
            duration_ms=template.duration_ms,
            context={
                "manifest_id": manifest.manifest_id,
                "manifest_sha256": manifest_hash,
                "source": "demo_seed",
            },
        )
        for template in manifest.events
    ]
    settings = Settings(database_url=DATABASE_URL, demo_user_id=user_id, _env_file=None)

    try:
        async with database.session_factory() as session, session.begin():
            session.add(User(id=user_id, display_name="M5 State Verifier"))
            session.add(_paper(seed_paper_id, seed_arxiv_id, 0))
            session.add_all(
                _paper(paper_id, f"m5.{suffix}.{rank}", rank)
                for rank, paper_id in enumerate(digest_paper_ids, start=1)
            )

        async with database.session_factory() as session:
            repository = EventRepository(session)
            async with session.begin():
                first_accepted = await repository.insert_events(
                    user_id, [event.to_record() for event in events]
                )
            async with session.begin():
                second_accepted = await repository.insert_events(
                    user_id, [event.to_record() for event in events]
                )

        assert first_accepted == len(events)
        assert second_accepted == 0
        assert await verify_persisted_seed_state(settings, manifest, events) == seed_paper_id
        assert await verify_persisted_seed_state(settings, manifest, events) == seed_paper_id

        async with database.session_factory() as session, session.begin():
            await session.execute(
                update(Paper)
                .where(Paper.id == seed_paper_id)
                .values(processing_status=ProcessingStatus.PARTIAL)
            )
        with pytest.raises(DemoSeedError, match="seed paper is unavailable"):
            await verify_persisted_seed_state(settings, manifest, events)
        async with database.session_factory() as session, session.begin():
            await session.execute(
                update(Paper)
                .where(Paper.id == seed_paper_id)
                .values(processing_status=ProcessingStatus.READY)
            )

        async with database.session_factory() as session, session.begin():
            await session.execute(
                update(UserEvent)
                .where(UserEvent.id == events[0].event_id)
                .values(
                    context={
                        "manifest_id": manifest.manifest_id,
                        "manifest_sha256": "0" * 64,
                        "source": "demo_seed",
                    }
                )
            )
        with pytest.raises(DemoSeedError, match="do not match"):
            await verify_persisted_seed_state(settings, manifest, events)
    finally:
        async with database.session_factory() as session, session.begin():
            await session.execute(delete(User).where(User.id == user_id))
            await session.execute(
                delete(Paper).where(Paper.id.in_((seed_paper_id, *digest_paper_ids)))
            )
        await database.dispose()


def test_demo_seed_event_replay_and_drift_checks_use_postgresql() -> None:
    asyncio.run(_exercise())
