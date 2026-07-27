"""PostgreSQL proof for briefing-paper to multi-node graph continuity."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, or_

from mneme.db.session import Database
from mneme.models.graph import Citation
from mneme.models.paper import Paper
from mneme.repositories.graph_queries import SqlGraphRepository
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.types import ArxivFeed
from mneme.services.seed_graph import SeedGraphCandidates, SeedGraphCandidateService
from mneme.services.semantic_scholar import SemanticPaper, SemanticScholarClient

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


def _paper(paper_id: UUID, *, arxiv_id: str, title: str) -> Paper:
    now = datetime.now(UTC)
    return Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        title=title,
        abstract=f"Abstract for {title}",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        published_at=now,
        source_updated_at=now,
    )


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    suffix = uuid4().hex[:12]
    seed_id = uuid4()
    candidate_ids = tuple(uuid4() for _ in range(5))
    seed_arxiv_id = f"m4.seed.{suffix}"
    candidate_arxiv_ids = tuple(f"m4.candidate.{suffix}.{index}" for index in range(5))
    seed_semantic_id = f"s2-seed-{suffix}"
    references = tuple(
        SemanticPaper(
            paperId=f"s2-candidate-{suffix}-{index}",
            externalIds={"ArXiv": arxiv_id},
        )
        for index, arxiv_id in enumerate(candidate_arxiv_ids)
    )
    candidates = SeedGraphCandidates(
        feed=ArxivFeed(records=(), total_results=0, start_index=0, items_per_page=0),
        center=SemanticPaper(
            paperId=seed_semantic_id,
            externalIds={"ArXiv": seed_arxiv_id},
        ),
        references=references,
        citations=(),
    )
    try:
        async with database.session_factory() as session, session.begin():
            session.add(_paper(seed_id, arxiv_id=seed_arxiv_id, title="Seed"))
            session.add_all(
                _paper(
                    paper_id,
                    arxiv_id=arxiv_id,
                    title=f"Candidate {index}",
                )
                for index, (paper_id, arxiv_id) in enumerate(
                    zip(candidate_ids, candidate_arxiv_ids, strict=True)
                )
            )

        async with database.session_factory() as session:
            service = SeedGraphCandidateService(
                cast(ArxivClient, MagicMock(spec=ArxivClient)),
                cast(SemanticScholarClient, MagicMock(spec=SemanticScholarClient)),
            )
            persistence = await service.persist(
                session,
                center_paper_id=seed_id,
                candidates=candidates,
            )
            assert persistence.references.inserted == 5

        async with database.session_factory() as session:
            graph = await SqlGraphRepository(session).get_ego_graph(
                candidate_ids[0],
                depth=2,
                max_nodes=50,
            )
            assert graph is not None
            assert graph.center_id == candidate_ids[0]
            assert len(graph.nodes) == 6
            assert len(graph.edges) == 5
            assert seed_id in graph.nodes
            assert set(candidate_ids).issubset(graph.nodes)
    finally:
        all_paper_ids = (seed_id, *candidate_ids)
        async with database.session_factory() as session, session.begin():
            await session.execute(
                delete(Citation).where(
                    or_(
                        Citation.source_paper_id.in_(all_paper_ids),
                        Citation.target_paper_id.in_(all_paper_ids),
                    )
                )
            )
            await session.execute(delete(Paper).where(Paper.id.in_(all_paper_ids)))
        await database.dispose()


def test_briefing_candidate_reaches_complete_seed_neighborhood_at_depth_two() -> None:
    asyncio.run(_exercise())
