"""PostgreSQL proof that later graph sync resolves external citations."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, or_, select

from mneme.db.session import Database
from mneme.models.graph import Citation
from mneme.models.paper import Paper
from mneme.services.semantic_scholar import (
    CitationDirection,
    SemanticPaper,
    SemanticScholarClient,
)
from mneme.services.semantic_scholar.sync import SemanticGraphSyncService

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


def _paper(
    paper_id: UUID,
    *,
    arxiv_id: str,
    title: str,
    semantic_scholar_id: str | None = None,
) -> Paper:
    now = datetime.now(UTC)
    return Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        semantic_scholar_id=semantic_scholar_id,
        title=title,
        abstract=f"Abstract for {title}",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        published_at=now,
        source_updated_at=now,
    )


def _service(
    database: Database,
    *,
    center_arxiv_id: str,
    center_semantic_id: str,
    neighbor_arxiv_id: str,
    neighbor_semantic_id: str,
) -> SemanticGraphSyncService:
    center = SemanticPaper(
        paperId=center_semantic_id,
        externalIds={"ArXiv": center_arxiv_id},
    )
    neighbor = SemanticPaper(
        paperId=neighbor_semantic_id,
        externalIds={"ArXiv": neighbor_arxiv_id},
    )
    client = AsyncMock(spec=SemanticScholarClient)
    client.fetch_papers.return_value = (center,)

    async def fetch_neighbors(
        _paper_id: str,
        direction: CitationDirection,
        *,
        limit: int,
    ) -> tuple[SemanticPaper, ...]:
        assert limit == 20
        return (neighbor,) if direction is CitationDirection.REFERENCES else ()

    client.fetch_neighbors.side_effect = fetch_neighbors
    return SemanticGraphSyncService(
        database.session_factory,
        cast(SemanticScholarClient, client),
    )


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    suffix = uuid4().hex[:12]
    center_id, neighbor_id = uuid4(), uuid4()
    center_arxiv_id = f"m3.resolve.{suffix}.1"
    center_semantic_id = f"s2-e2e-center-{suffix}"
    neighbor_arxiv_id = f"m3.resolve.{suffix}.2"
    neighbor_semantic_id = f"s2-e2e-neighbor-{suffix}"
    service = _service(
        database,
        center_arxiv_id=center_arxiv_id,
        center_semantic_id=center_semantic_id,
        neighbor_arxiv_id=neighbor_arxiv_id,
        neighbor_semantic_id=neighbor_semantic_id,
    )
    try:
        async with database.session_factory() as session, session.begin():
            session.add(_paper(center_id, arxiv_id=center_arxiv_id, title="Resolution center"))

        first = await service.sync(paper_id=center_id, limit=20)
        assert first.references.inserted == 1
        assert first.references.resolved == 0
        async with database.session_factory() as session:
            unresolved = await session.scalar(
                select(Citation).where(Citation.source_paper_id == center_id)
            )
        assert unresolved is not None
        assert unresolved.target_paper_id is None
        assert unresolved.external_target_id == neighbor_semantic_id

        async with database.session_factory() as session, session.begin():
            session.add(
                _paper(
                    neighbor_id,
                    arxiv_id=neighbor_arxiv_id,
                    title="Later local neighbor",
                    semantic_scholar_id=neighbor_semantic_id,
                )
            )

        resolved = await service.sync(paper_id=center_id, limit=20)
        replay = await service.sync(paper_id=center_id, limit=20)
        assert resolved.references.inserted == 0
        assert (resolved.references.resolved, resolved.references.duplicates) == (1, 1)
        assert replay.references.inserted == 0
        assert (replay.references.resolved, replay.references.duplicates) == (0, 1)

        async with database.session_factory() as session:
            edge_count = await session.scalar(
                select(func.count(Citation.id)).where(Citation.source_paper_id == center_id)
            )
            edge = await session.scalar(
                select(Citation).where(Citation.source_paper_id == center_id)
            )
        assert edge_count == 1
        assert edge is not None and edge.target_paper_id == neighbor_id
        assert edge.external_target_id is None
    finally:
        async with database.session_factory() as session, session.begin():
            await session.execute(
                delete(Citation).where(
                    or_(
                        Citation.source_paper_id.in_((center_id, neighbor_id)),
                        Citation.target_paper_id.in_((center_id, neighbor_id)),
                    )
                )
            )
            await session.execute(delete(Paper).where(Paper.id.in_((center_id, neighbor_id))))
        await database.dispose()


def test_later_local_paper_is_resolved_and_replay_is_idempotent() -> None:
    asyncio.run(_exercise())
