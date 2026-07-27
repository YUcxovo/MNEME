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
from mneme.models.digest import Digest, DigestType
from mneme.models.graph import Citation
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.models.user import User, UserEvent, UserPreference
from mneme.services.recommendation import GENERATOR_VERSION

DATABASE_URL = os.getenv("MNEME_DATABASE_URL", "")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(UTC)
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
    old_version, latest_version, outgoing_version = uuid4(), uuid4(), uuid4()
    x_axis = [1.0, 0.0, *([0.0] * 1534)]
    y_axis = [0.0, 1.0, *([0.0] * 1534)]
    async with database.session_factory() as session, session.begin():
        session.add(User(id=ids.user, display_name=f"M3 User {suffix}"))
        session.add_all(
            [
                _paper(ids.center, f"m3.{suffix}.1", "Center paper"),
                _paper(ids.incoming, f"m3.{suffix}.2", "Incoming paper"),
                _paper(ids.outgoing, f"m3.{suffix}.3", "Outgoing paper"),
            ]
        )
        await session.flush()
        session.add(
            UserPreference(
                user_id=ids.user,
                explicit_topics=["attention"],
                followed_authors=["Ada Researcher"],
            )
        )
        session.add_all(
            [
                PaperVersion(id=old_version, paper_id=ids.center, version_number=1),
                PaperVersion(id=latest_version, paper_id=ids.center, version_number=2),
                PaperVersion(id=outgoing_version, paper_id=ids.outgoing, version_number=1),
            ]
        )
        await session.flush()
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
                _chunk(
                    paper_id=ids.outgoing,
                    version_id=outgoing_version,
                    chunk_index=0,
                    embedding=y_axis,
                ),
                Citation(source_paper_id=ids.incoming, target_paper_id=ids.center),
                Citation(source_paper_id=ids.center, target_paper_id=ids.outgoing),
                Digest(
                    user_id=ids.user,
                    digest_type=DigestType.MANUAL,
                    preference_model_version=1,
                    generator_version="recommender-v1",
                ),
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
    saved_event_id = uuid4()
    impression_event_id = uuid4()
    skipped_event_id = uuid4()
    headers = {"Authorization": f"Bearer {token}"}
    events = [
        {
            "event_id": str(saved_event_id),
            "event_type": "paper_saved",
            "paper_id": str(ids.center),
            "occurred_at": NOW.isoformat(),
        },
        {
            "event_id": str(impression_event_id),
            "event_type": "paper_impression",
            "paper_id": str(ids.outgoing),
            "occurred_at": NOW.isoformat(),
        },
        {
            "event_id": str(skipped_event_id),
            "event_type": "paper_skipped",
            "paper_id": str(ids.outgoing),
            "occurred_at": NOW.isoformat(),
        },
    ]
    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            accepted = await client.post("/v1/events", json=events, headers=headers)
            replay = await client.post("/v1/events", json=events, headers=headers)
            unknown = await client.post(
                "/v1/events",
                json=[
                    {**events[0], "event_id": str(uuid4())},
                    {**events[0], "event_id": str(uuid4()), "paper_id": str(uuid4())},
                ],
                headers=headers,
            )
            recommended = await client.post("/v1/digests/recommended", headers=headers)
            graph = await client.get(f"/v1/graph/{ids.center}?depth=1&limit=3", headers=headers)
            bounded = await client.get(f"/v1/graph/{ids.center}?depth=1&limit=1", headers=headers)

        assert accepted.json() == {"accepted": 3, "duplicates": 0}
        assert replay.json() == {"accepted": 0, "duplicates": 3}
        assert unknown.status_code == 404
        assert recommended.status_code == 200
        assert recommended.json()["entries"] == []
        assert graph.status_code == 200
        assert {UUID(node["id"]) for node in graph.json()["nodes"]} == set(ids.papers)
        assert len(bounded.json()["nodes"]) == 1
        assert bounded.json()["nodes"][0]["id"] == str(ids.center)

        async with database.session_factory() as session:
            event_count = await session.scalar(
                select(func.count(UserEvent.id)).where(UserEvent.user_id == ids.user)
            )
            preference = await session.get(UserPreference, ids.user)
            digests = list(
                (
                    await session.scalars(
                        select(Digest)
                        .where(Digest.user_id == ids.user)
                        .order_by(Digest.generated_at)
                    )
                ).all()
            )
        assert event_count == 3
        assert preference is not None and preference.behavior_embedding is not None
        assert preference.negative_behavior_embedding is not None
        assert preference.behavior_embedding_model == EMBEDDING_MODEL
        assert preference.model_version == 2
        assert 0 < preference.behavior_confidence < 1
        assert preference.behavior_embedding[0] == pytest.approx(1.0)
        assert preference.behavior_embedding[1] == pytest.approx(0.0)
        assert preference.negative_behavior_embedding[0] == pytest.approx(0.0)
        assert preference.negative_behavior_embedding[1] == pytest.approx(1.0)
        assert preference.behavior_evidence["model_name"] == "behavior-v2"
        assert preference.behavior_evidence["ignored_unexposed_negative_count"] == 0
        assert preference.explicit_topics == ["attention"]
        assert preference.followed_authors == ["Ada Researcher"]
        digests_by_generator = {digest.generator_version: digest for digest in digests}
        assert set(digests_by_generator) == {"recommender-v1", GENERATOR_VERSION}
        assert digests_by_generator[GENERATOR_VERSION].preference_model_version == 2
    finally:
        await _cleanup(database, ids)
        await application.state.redis.aclose()
        await application.state.database.dispose()
        await database.dispose()


def test_m3_behavior_and_graph_platform_loop() -> None:
    asyncio.run(_exercise())
