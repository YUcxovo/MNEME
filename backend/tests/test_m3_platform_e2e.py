"""PostgreSQL proof of the M3 behavior and citation-graph platform loop."""

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, or_, select

from mneme.core.config import Environment, Settings
from mneme.core.security import token_sha256
from mneme.db.session import Database
from mneme.main import create_app
from mneme.models.artifact import PaperChunk
from mneme.models.graph import Citation
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.models.user import User, UserEvent, UserPreference

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
EMBEDDING_MODEL = "m3-e2e-embedding-v1"

pytestmark = [pytest.mark.db, pytest.mark.api, pytest.mark.pipeline, pytest.mark.rag]

if not DATABASE_URL:
    pytest.skip(
        "MNEME_DATABASE_URL is not configured for PostgreSQL integration tests",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def upgrade_database() -> None:
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")


@dataclass(frozen=True, slots=True)
class FixtureIds:
    user: UUID
    center: UUID
    incoming: UUID
    outgoing: UUID
    papers: tuple[UUID, ...]


def _paper(paper_id: UUID, arxiv_id: str, title: str) -> Paper:
    return Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        title=title,
        abstract=f"Abstract for {title}",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        processing_status=ProcessingStatus.READY,
        published_at=NOW,
        source_updated_at=NOW,
    )


def _chunk(
    *,
    paper_id: UUID,
    version_id: UUID,
    chunk_index: int,
    embedding: list[float],
    model: str = EMBEDDING_MODEL,
) -> PaperChunk:
    return PaperChunk(
        paper_id=paper_id,
        paper_version_id=version_id,
        chunk_index=chunk_index,
        content=f"chunk-{chunk_index}",
        content_hash=f"{chunk_index:064x}",
        embedding=embedding,
        embedding_model=model,
    )


async def _seed(database: Database) -> FixtureIds:
    suffix = uuid4().hex[:12]
    ids = FixtureIds(
        user=uuid4(),
        center=uuid4(),
        incoming=uuid4(),
        outgoing=uuid4(),
        papers=(),
    )
    ids = FixtureIds(
        user=ids.user,
        center=ids.center,
        incoming=ids.incoming,
        outgoing=ids.outgoing,
        papers=(ids.center, ids.incoming, ids.outgoing),
    )
    old_version, latest_version = uuid4(), uuid4()
    x_axis = [1.0, 0.0, *([0.0] * 1534)]
    y_axis = [0.0, 1.0, *([0.0] * 1534)]
    async with database.session_factory() as session, session.begin():
        session.add(User(id=ids.user, display_name=f"M3 User {suffix}"))
        session.add(UserPreference(user_id=ids.user, explicit_topics=[], followed_authors=[]))
        session.add_all(
            [
                _paper(ids.center, f"m3.{suffix}.1", "Center paper"),
                _paper(ids.incoming, f"m3.{suffix}.2", "Incoming paper"),
                _paper(ids.outgoing, f"m3.{suffix}.3", "Outgoing paper"),
                PaperVersion(id=old_version, paper_id=ids.center, version_number=1),
                PaperVersion(id=latest_version, paper_id=ids.center, version_number=2),
            ]
        )
        session.add_all(
            [
                _chunk(
                    paper_id=ids.center, version_id=old_version, chunk_index=0, embedding=y_axis
                ),
                _chunk(
                    paper_id=ids.center, version_id=latest_version, chunk_index=0, embedding=x_axis
                ),
                _chunk(
                    paper_id=ids.center,
                    version_id=latest_version,
                    chunk_index=1,
                    embedding=y_axis,
                    model="other-model",
                ),
                Citation(source_paper_id=ids.incoming, target_paper_id=ids.center),
                Citation(source_paper_id=ids.center, target_paper_id=ids.outgoing),
            ]
        )
    return ids


async def _cleanup(database: Database, ids: FixtureIds) -> None:
    async with database.session_factory() as session, session.begin():
        await session.execute(
            delete(Citation).where(
                or_(
                    Citation.source_paper_id.in_(ids.papers),
                    Citation.target_paper_id.in_(ids.papers),
                )
            )
        )
        await session.execute(delete(User).where(User.id == ids.user))
        await session.execute(delete(Paper).where(Paper.id.in_(ids.papers)))


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    ids = await _seed(database)
    token = f"m3-token-{uuid4().hex}"
    application = create_app(
        Settings(
            environment=Environment.TESTING,
            database_url=DATABASE_URL,
            demo_user_id=ids.user,
            demo_token_sha256=token_sha256(token),
            ai_embedding_model=EMBEDDING_MODEL,
            _env_file=None,
        )
    )
    event_id = uuid4()
    headers = {"Authorization": f"Bearer {token}"}
    event = {
        "event_id": str(event_id),
        "event_type": "paper_saved",
        "paper_id": str(ids.center),
        "occurred_at": NOW.isoformat(),
    }
    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            accepted = await client.post("/v1/events", json=[event], headers=headers)
            replay = await client.post("/v1/events", json=[event], headers=headers)
            unknown = await client.post(
                "/v1/events",
                json=[
                    {**event, "event_id": str(uuid4())},
                    {**event, "event_id": str(uuid4()), "paper_id": str(uuid4())},
                ],
                headers=headers,
            )
            graph = await client.get(f"/v1/graph/{ids.center}?depth=1&limit=3", headers=headers)
            bounded = await client.get(f"/v1/graph/{ids.center}?depth=1&limit=1", headers=headers)

        assert accepted.json() == {"accepted": 1, "duplicates": 0}
        assert replay.json() == {"accepted": 0, "duplicates": 1}
        assert unknown.status_code == 404
        assert graph.status_code == 200
        assert {UUID(node["id"]) for node in graph.json()["nodes"]} == set(ids.papers)
        assert len(bounded.json()["nodes"]) == 1
        assert bounded.json()["nodes"][0]["id"] == str(ids.center)

        async with database.session_factory() as session:
            event_count = await session.scalar(
                select(func.count(UserEvent.id)).where(UserEvent.user_id == ids.user)
            )
            preference = await session.get(UserPreference, ids.user)
        assert event_count == 1
        assert preference is not None and preference.behavior_embedding is not None
        assert preference.behavior_embedding_model == EMBEDDING_MODEL
        assert preference.behavior_embedding[0] == pytest.approx(1.0)
        assert preference.behavior_embedding[1] == pytest.approx(0.0)
    finally:
        await _cleanup(database, ids)
        await application.state.redis.aclose()
        await application.state.database.dispose()
        await database.dispose()


def test_m3_behavior_and_graph_platform_loop() -> None:
    asyncio.run(_exercise())
