"""PostgreSQL proof for idempotent local graph preparation persistence."""

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
from sqlalchemy import delete, or_, select

from mneme.db.session import Database
from mneme.models.artifact import PaperChunk
from mneme.models.graph import Citation
from mneme.models.paper import Paper, PaperVersion
from mneme.repositories.citation_graph import (
    GRAPH_PREPARED_AS_SOURCE,
    GRAPH_PREPARED_AS_TARGET,
    CitationGraphRepository,
    LocalCitationPersistenceResult,
)
from mneme.repositories.graph_preparation import GraphPreparationRepository
from mneme.repositories.graph_queries import SqlGraphRepository
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.types import (
    ArxivAuthorRecord,
    ArxivFeed,
    ArxivPaperRecord,
)

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


def _record(arxiv_id: str, title: str) -> ArxivPaperRecord:
    now = datetime.now(UTC)
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=1,
        title=title,
        abstract=f"Abstract for {title}",
        authors=(ArxivAuthorRecord(name=f"Author for {title}"),),
        categories=("cs.AI",),
        primary_category="cs.AI",
        published_at=now,
        updated_at=now,
        abstract_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        source_license=None,
        doi=None,
        comment=None,
        journal_reference=None,
    )


async def _exercise() -> None:
    database = Database(DATABASE_URL)
    suffix = int(uuid4().hex[:8], 16) % 100000
    center_id = uuid4()
    older_version_id = uuid4()
    newer_version_id = uuid4()
    center_arxiv_id = f"9999.{suffix:05d}"
    reference_arxiv_id = f"9998.{suffix:05d}"
    citation_arxiv_id = f"9997.{suffix:05d}"
    concurrent_source_id = uuid4()
    concurrent_target_id = uuid4()
    concurrent_source_arxiv_id = f"9996.{suffix:05d}"
    concurrent_target_arxiv_id = f"9995.{suffix:05d}"
    now = datetime.now(UTC)
    feed = ArxivFeed(
        records=(
            _record(reference_arxiv_id, "Reference"),
            _record(citation_arxiv_id, "Citation"),
        ),
        total_results=2,
        start_index=0,
        items_per_page=2,
    )
    all_arxiv_ids = (
        center_arxiv_id,
        reference_arxiv_id,
        citation_arxiv_id,
        concurrent_source_arxiv_id,
        concurrent_target_arxiv_id,
    )
    try:
        async with database.session_factory() as session, session.begin():
            session.add(
                Paper(
                    id=center_id,
                    arxiv_id=center_arxiv_id,
                    title="Center",
                    abstract="Center abstract",
                    primary_category="cs.AI",
                    categories=["cs.AI"],
                    pdf_url=f"https://arxiv.org/pdf/{center_arxiv_id}",
                    published_at=now,
                    source_updated_at=now,
                )
            )
            session.add_all(
                [
                    Paper(
                        id=concurrent_source_id,
                        arxiv_id=concurrent_source_arxiv_id,
                        title="Concurrent source",
                        abstract="Concurrent source abstract",
                        primary_category="cs.AI",
                        categories=["cs.AI"],
                        pdf_url=f"https://arxiv.org/pdf/{concurrent_source_arxiv_id}",
                        published_at=now,
                        source_updated_at=now,
                    ),
                    Paper(
                        id=concurrent_target_id,
                        arxiv_id=concurrent_target_arxiv_id,
                        title="Concurrent target",
                        abstract="Concurrent target abstract",
                        primary_category="cs.AI",
                        categories=["cs.AI"],
                        pdf_url=f"https://arxiv.org/pdf/{concurrent_target_arxiv_id}",
                        published_at=now,
                        source_updated_at=now,
                    ),
                ]
            )
            session.add_all(
                [
                    PaperVersion(
                        id=older_version_id,
                        paper_id=center_id,
                        version_number=1,
                    ),
                    PaperVersion(
                        id=newer_version_id,
                        paper_id=center_id,
                        version_number=2,
                    ),
                ]
            )
            session.add_all(
                [
                    PaperChunk(
                        paper_id=center_id,
                        paper_version_id=older_version_id,
                        section_title="References",
                        chunk_index=0,
                        content=f"arXiv:{reference_arxiv_id}",
                        content_hash="a" * 64,
                    ),
                    PaperChunk(
                        paper_id=center_id,
                        paper_version_id=newer_version_id,
                        section_title="Cross References",
                        chunk_index=0,
                        content=f"arXiv:{citation_arxiv_id}",
                        content_hash="b" * 64,
                    ),
                ]
            )

        repository = GraphPreparationRepository(database.session_factory)
        assert await repository.list_reference_chunks(center_id) == (f"arXiv:{reference_arxiv_id}",)
        fake_arxiv = cast(ArxivClient, MagicMock(spec=ArxivClient))
        first = await repository.persist_candidates(
            arxiv_client=fake_arxiv,
            feed=feed,
            center_paper_id=center_id,
            reference_arxiv_ids=(reference_arxiv_id,),
            citation_arxiv_ids=(citation_arxiv_id,),
            evidence_source="openalex",
        )
        second = await repository.persist_candidates(
            arxiv_client=fake_arxiv,
            feed=feed,
            center_paper_id=center_id,
            reference_arxiv_ids=(reference_arxiv_id,),
            citation_arxiv_ids=(citation_arxiv_id,),
            evidence_source="openalex",
        )

        assert first is not None and (first.inserted, first.duplicates) == (2, 0)
        assert second is not None and (second.inserted, second.duplicates) == (0, 2)
        assert await repository.has_prepared_neighborhood(center_id)
        async with database.session_factory() as session:
            graph = await SqlGraphRepository(session).get_ego_graph(
                center_id,
                depth=1,
                max_nodes=10,
            )
        assert graph is not None
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        async with database.session_factory() as session:
            reference_id = await session.scalar(
                select(Paper.id).where(Paper.arxiv_id == reference_arxiv_id)
            )
            citation_id = await session.scalar(
                select(Paper.id).where(Paper.arxiv_id == citation_arxiv_id)
            )
        assert reference_id is not None
        assert citation_id is not None
        assert not await repository.has_prepared_neighborhood(reference_id)
        assert not await repository.has_prepared_neighborhood(citation_id)

        reverse = await repository.persist_candidates(
            arxiv_client=fake_arxiv,
            feed=ArxivFeed(records=(), total_results=0, start_index=0, items_per_page=0),
            center_paper_id=reference_id,
            reference_arxiv_ids=(),
            citation_arxiv_ids=(center_arxiv_id,),
            evidence_source="semantic_scholar",
        )
        assert reverse is not None and (reverse.inserted, reverse.duplicates) == (0, 1)
        assert await repository.has_prepared_neighborhood(reference_id)
        async with database.session_factory() as session:
            shared_edge = await session.scalar(
                select(Citation).where(
                    Citation.source_paper_id == center_id,
                    Citation.target_paper_id == reference_id,
                )
            )
        assert shared_edge is not None
        assert shared_edge.algorithm_metadata[GRAPH_PREPARED_AS_SOURCE] is True
        assert shared_edge.algorithm_metadata[GRAPH_PREPARED_AS_TARGET] is True

        citation_repository = CitationGraphRepository()

        async def persist_concurrently(
            *,
            center_paper_id: UUID,
            reference_arxiv_ids: tuple[str, ...],
            citation_arxiv_ids: tuple[str, ...],
        ) -> LocalCitationPersistenceResult | None:
            async with database.session_factory() as session, session.begin():
                return await citation_repository.persist_local_arxiv_edges(
                    session,
                    center_paper_id=center_paper_id,
                    reference_arxiv_ids=reference_arxiv_ids,
                    citation_arxiv_ids=citation_arxiv_ids,
                    evidence_source="openalex",
                )

        concurrent_results = await asyncio.wait_for(
            asyncio.gather(
                persist_concurrently(
                    center_paper_id=concurrent_source_id,
                    reference_arxiv_ids=(concurrent_target_arxiv_id,),
                    citation_arxiv_ids=(),
                ),
                persist_concurrently(
                    center_paper_id=concurrent_target_id,
                    reference_arxiv_ids=(),
                    citation_arxiv_ids=(concurrent_source_arxiv_id,),
                ),
            ),
            timeout=5,
        )
        assert all(result is not None for result in concurrent_results)
        assert sum(result.inserted for result in concurrent_results if result is not None) == 1
        assert await repository.has_prepared_neighborhood(concurrent_source_id)
        assert await repository.has_prepared_neighborhood(concurrent_target_id)
    finally:
        async with database.session_factory() as session, session.begin():
            paper_ids = (
                await session.scalars(select(Paper.id).where(Paper.arxiv_id.in_(all_arxiv_ids)))
            ).all()
            if paper_ids:
                await session.execute(
                    delete(Citation).where(
                        or_(
                            Citation.source_paper_id.in_(paper_ids),
                            Citation.target_paper_id.in_(paper_ids),
                        )
                    )
                )
                await session.execute(delete(Paper).where(Paper.id.in_(paper_ids)))
        await database.dispose()


def test_graph_preparation_persists_real_edges_idempotently() -> None:
    asyncio.run(_exercise())
