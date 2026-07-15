"""Gated PostgreSQL integration tests for M1 persistence and catalog APIs."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from mneme.core.config import Environment, Settings
from mneme.core.security import token_sha256
from mneme.db.dependencies import get_database
from mneme.db.session import Database
from mneme.main import create_app
from mneme.models.paper import Author, Paper, PaperVersion
from mneme.models.user import User, UserPreference
from mneme.repositories.arxiv_ingestion import ArxivIngestionRepository, normalize_author_name
from mneme.repositories.paper_catalog import PaperCatalogRepository
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivPaperRecord

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.db, pytest.mark.api, pytest.mark.pipeline]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    """Apply the complete migration chain before exercising repositories."""
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


def _record(
    arxiv_id: str,
    *,
    version: int,
    title: str,
    updated_at: datetime,
    authors: tuple[str, ...],
    category: str = "cs.AI",
) -> ArxivPaperRecord:
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=version,
        title=title,
        abstract=f"Abstract for {title}",
        authors=tuple(ArxivAuthorRecord(name) for name in authors),
        categories=(category,),
        primary_category=category,
        published_at=updated_at - timedelta(days=1),
        updated_at=updated_at,
        abstract_url=f"https://arxiv.org/abs/{arxiv_id}v{version}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}v{version}",
        source_license="http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        doi=None,
        comment=None,
        journal_reference=None,
    )


async def _delete_fixture_rows(
    database: Database,
    *,
    arxiv_ids: tuple[str, ...],
    author_names: tuple[str, ...],
    user_id: UUID | None = None,
) -> None:
    normalized_names = [normalize_author_name(name)[1] for name in author_names]
    async with database.session_factory() as session, session.begin():
        if user_id is not None:
            await session.execute(delete(User).where(User.id == user_id))
        await session.execute(delete(Paper).where(Paper.arxiv_id.in_(arxiv_ids)))
        await session.execute(delete(Author).where(Author.normalized_name.in_(normalized_names)))


async def _exercise_arxiv_repository() -> None:
    database = Database(DATABASE_URL)
    suffix = uuid4().hex[:12]
    arxiv_id = f"test.{suffix}"
    author_names = (f"Alice {suffix}", f"Bob {suffix}", f"Carol {suffix}", f"Stale {suffix}")
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)
    original = _record(
        arxiv_id,
        version=1,
        title="Original snapshot",
        updated_at=timestamp,
        authors=author_names[:2],
    )
    newest = _record(
        arxiv_id,
        version=2,
        title="Newest snapshot",
        updated_at=timestamp + timedelta(days=2),
        authors=(author_names[2], author_names[0]),
    )
    stale = _record(
        arxiv_id,
        version=3,
        title="Stale snapshot",
        updated_at=timestamp - timedelta(days=2),
        authors=(author_names[3],),
    )
    repository = ArxivIngestionRepository()

    try:
        async with database.session_factory() as session, session.begin():
            original_result = await repository.upsert_record(session, original)
            newest_result = await repository.upsert_record(session, newest)
            stale_result = await repository.upsert_record(session, stale)
            replay_result = await repository.upsert_record(session, newest)

        assert original_result.paper_id == newest_result.paper_id == stale_result.paper_id
        assert [
            original_result.version_created,
            newest_result.version_created,
            stale_result.version_created,
            replay_result.version_created,
        ] == [True, True, True, False]
        assert stale_result.authors_replaced is False

        async with database.session_factory() as session:
            paper = await PaperCatalogRepository(session).get_paper(original_result.paper_id)
            versions = list(
                (
                    await session.scalars(
                        select(PaperVersion.version_number)
                        .where(PaperVersion.paper_id == original_result.paper_id)
                        .order_by(PaperVersion.version_number)
                    )
                ).all()
            )

        assert paper is not None
        assert paper.title == newest.title
        assert paper.source_updated_at == newest.updated_at
        assert [link.author.display_name for link in paper.author_links] == [
            author_names[2],
            author_names[0],
        ]
        assert versions == [1, 2, 3]
    finally:
        await _delete_fixture_rows(
            database,
            arxiv_ids=(arxiv_id,),
            author_names=author_names,
        )
        await database.dispose()


def test_arxiv_repository_preserves_newest_snapshot_and_idempotent_versions() -> None:
    asyncio.run(_exercise_arxiv_repository())


async def _exercise_authenticated_catalog_api() -> None:
    suffix = uuid4().hex[:12]
    arxiv_ids = (f"api.{suffix}.1", f"api.{suffix}.2")
    author_names = (f"API Author {suffix}", f"Second Author {suffix}")
    user_id = uuid4()
    token = f"integration-token-{suffix}"
    timestamp = datetime(2099, 1, 2, tzinfo=UTC)
    records = tuple(
        _record(
            arxiv_id,
            version=1,
            title=f"API paper {index}",
            updated_at=timestamp - timedelta(days=index),
            authors=(author_names[index - 1],),
            category=f"test.{suffix}",
        )
        for index, arxiv_id in enumerate(arxiv_ids, start=1)
    )
    settings = Settings(
        environment=Environment.TESTING,
        database_url=DATABASE_URL,
        demo_token_sha256=token_sha256(token),
        demo_user_id=user_id,
        _env_file=None,
    )
    application = create_app(settings)
    database: Database = application.state.database
    paper_ids: list[UUID] = []

    async def database_override() -> Database:
        return database

    application.dependency_overrides[get_database] = database_override

    try:
        async with database.session_factory() as session, session.begin():
            session.add(User(id=user_id, display_name=f"Integration User {suffix}"))
            session.add(
                UserPreference(
                    user_id=user_id,
                    explicit_topics=["initial topic"],
                    followed_authors=[],
                )
            )
            ingestion = ArxivIngestionRepository()
            for record in records:
                result = await ingestion.upsert_record(session, record)
                paper_ids.append(result.paper_id)

        transport = ASGITransport(app=application)
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first_page = await client.get("/v1/papers", params={"limit": 1}, headers=headers)
            assert first_page.status_code == 200
            first_payload = first_page.json()
            assert first_payload["next_cursor"] is not None

            second_page = await client.get(
                "/v1/papers",
                params={"limit": 1, "cursor": first_payload["next_cursor"]},
                headers=headers,
            )
            assert second_page.status_code == 200
            assert second_page.json()["items"][0]["id"] != first_payload["items"][0]["id"]

            detail = await client.get(f"/v1/papers/{paper_ids[0]}", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["title"] == records[0].title
            assert detail.json()["authors"] == [author_names[0]]

            initial = await client.get("/v1/users/me/preferences", headers=headers)
            assert initial.status_code == 200
            assert initial.json()["topics"] == ["initial topic"]

            changed = await client.put(
                "/v1/users/me/preferences",
                headers=headers,
                json={
                    "topics": [" Graph Learning ", "NLP"],
                    "followed_authors": [" Test Author "],
                },
            )
            assert changed.status_code == 200
            assert changed.json()["topics"] == ["graph learning", "nlp"]
            changed_at = changed.json()["updated_at"]

            replay = await client.put(
                "/v1/users/me/preferences",
                headers=headers,
                json={
                    "topics": ["GRAPH LEARNING", " graph learning ", " nlp "],
                    "followed_authors": ["TEST AUTHOR"],
                },
            )
            assert replay.status_code == 200
            assert replay.json()["updated_at"] == changed_at
    finally:
        await _delete_fixture_rows(
            database,
            arxiv_ids=arxiv_ids,
            author_names=author_names,
            user_id=user_id,
        )
        await application.state.redis.aclose()
        await database.dispose()


def test_authenticated_catalog_and_preferences_use_real_repositories() -> None:
    asyncio.run(_exercise_authenticated_catalog_api())
