"""PostgreSQL proof for tied-timestamp digest keyset pagination."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete

from mneme.db.session import Database
from mneme.models.digest import Digest, DigestType
from mneme.models.user import User
from mneme.repositories.digests import DigestRepository, decode_digest_cursor

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.db, pytest.mark.api]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


async def _exercise_tied_keyset() -> None:
    database = Database(DATABASE_URL)
    user_id, other_user_id = uuid4(), uuid4()
    digest_ids = tuple(uuid4() for _ in range(4))
    generated_at = datetime(2199, 2, 1, 12, tzinfo=UTC)
    try:
        async with database.session_factory() as session, session.begin():
            session.add_all(
                [
                    User(id=user_id, display_name="Digest pagination owner"),
                    User(id=other_user_id, display_name="Digest pagination other user"),
                ]
            )
            session.add_all(
                [
                    Digest(
                        id=digest_id,
                        user_id=user_id,
                        digest_type=DigestType.WEEKLY,
                        generated_at=generated_at,
                        preference_model_version=1,
                        generator_version="pagination-test-v1",
                    )
                    for digest_id in digest_ids
                ]
            )
            session.add(
                Digest(
                    user_id=other_user_id,
                    digest_type=DigestType.MANUAL,
                    generated_at=generated_at,
                    preference_model_version=1,
                    generator_version="pagination-test-v1",
                )
            )

        async with database.session_factory() as session:
            repository = DigestRepository(session)
            first = await repository.list_digests(user_id=user_id, limit=2)
            assert first.next_cursor is not None
            second = await repository.list_digests(
                user_id=user_id,
                limit=2,
                cursor=decode_digest_cursor(first.next_cursor),
            )

        observed = [item.id for item in (*first.items, *second.items)]
        assert observed == sorted(digest_ids, reverse=True)
        assert len(observed) == len(set(observed)) == 4
        assert second.next_cursor is None
    finally:
        async with database.session_factory() as session, session.begin():
            await session.execute(delete(User).where(User.id.in_((user_id, other_user_id))))
        await database.dispose()


def test_digest_keyset_has_no_gaps_duplicates_or_user_leakage() -> None:
    asyncio.run(_exercise_tied_keyset())
