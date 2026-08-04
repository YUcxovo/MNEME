"""PostgreSQL isolation proof for the local demo-user reset."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select

from mneme.cli import reset_demo_user
from mneme.core.config import Settings
from mneme.db.session import Database
from mneme.models.digest import Digest, DigestType
from mneme.models.paper import Paper, ProcessingStatus
from mneme.models.qa import QaConversation
from mneme.models.user import User, UserEvent, UserEventType, UserPreference

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.db

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def exercise_reset_isolation() -> None:
    database = Database(DATABASE_URL)
    target_user_id = uuid4()
    other_user_id = uuid4()
    paper_id = uuid4()
    now = datetime.now(UTC)
    suffix = uuid4().hex[:12]
    try:
        async with database.session_factory() as session:
            session.add_all(
                [
                    User(id=target_user_id, display_name="Reset Target"),
                    User(id=other_user_id, display_name="Reset Control"),
                    Paper(
                        id=paper_id,
                        arxiv_id=f"demo-reset.{suffix}",
                        title="Shared reset-isolation paper",
                        abstract="A shared catalog row that must survive demo-user reset.",
                        primary_category="cs.SE",
                        categories=["cs.SE"],
                        pdf_url=f"https://arxiv.org/pdf/demo-reset.{suffix}v1",
                        processing_status=ProcessingStatus.METADATA_ONLY,
                        published_at=now,
                        source_updated_at=now,
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    UserPreference(
                        user_id=target_user_id,
                        explicit_topics=["cs.SE"],
                        followed_authors=["Target Author"],
                        behavior_confidence=0.5,
                        behavior_evidence={"events": 1},
                        model_version=2,
                    ),
                    UserPreference(
                        user_id=other_user_id,
                        explicit_topics=["cs.AI"],
                        followed_authors=["Control Author"],
                    ),
                    UserEvent(
                        user_id=target_user_id,
                        paper_id=paper_id,
                        event_type=UserEventType.PAPER_OPENED,
                        occurred_at=now,
                        context={"source": "test"},
                    ),
                    UserEvent(
                        user_id=other_user_id,
                        paper_id=paper_id,
                        event_type=UserEventType.PAPER_SAVED,
                        occurred_at=now,
                        context={"source": "control"},
                    ),
                    Digest(
                        user_id=target_user_id,
                        digest_type=DigestType.MANUAL,
                        preference_model_version=2,
                        generator_version="reset-test",
                    ),
                    Digest(
                        user_id=other_user_id,
                        digest_type=DigestType.MANUAL,
                        preference_model_version=1,
                        generator_version="reset-control",
                    ),
                    QaConversation(user_id=target_user_id, paper_id=paper_id),
                    QaConversation(user_id=other_user_id, paper_id=paper_id),
                ]
            )
            await session.commit()

        settings = Settings(
            database_url=DATABASE_URL,
            demo_user_id=target_user_id,
            _env_file=None,
        )
        first = await reset_demo_user.run(settings)
        second = await reset_demo_user.run(settings)

        assert first.deleted_events == 1
        assert first.deleted_digests == 1
        assert first.deleted_qa_conversations == 1
        assert second.deleted_events == 0
        assert second.deleted_digests == 0
        assert second.deleted_qa_conversations == 0

        async with database.session_factory() as session:
            target_preference = await session.get(UserPreference, target_user_id)
            other_preference = await session.get(UserPreference, other_user_id)
            assert target_preference is not None
            assert target_preference.explicit_topics == []
            assert target_preference.followed_authors == []
            assert target_preference.behavior_confidence == 0.0
            assert target_preference.behavior_evidence == {}
            assert target_preference.model_version == 1
            assert other_preference is not None
            assert other_preference.explicit_topics == ["cs.AI"]
            assert other_preference.followed_authors == ["Control Author"]

            assert (
                await session.scalar(
                    select(func.count(UserEvent.id)).where(UserEvent.user_id == other_user_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(Digest.id)).where(Digest.user_id == other_user_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(QaConversation.id)).where(
                        QaConversation.user_id == other_user_id
                    )
                )
                == 1
            )
            assert await session.get(Paper, paper_id) is not None
    finally:
        async with database.session_factory() as session:
            await session.execute(delete(User).where(User.id.in_((target_user_id, other_user_id))))
            await session.commit()
            await session.execute(delete(Paper).where(Paper.id == paper_id))
            await session.commit()
        await database.dispose()


def test_reset_only_changes_the_configured_user() -> None:
    asyncio.run(exercise_reset_isolation())
