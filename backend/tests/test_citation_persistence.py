"""Unit tests for idempotent Semantic Scholar citation persistence."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.graph import Citation
from mneme.models.paper import Paper
from mneme.repositories.citation_graph import (
    GRAPH_PREPARED_AS_SOURCE,
    GRAPH_PREPARED_AS_TARGET,
    CitationGraphRepository,
    CitationIdentityConflict,
    CitationPersistenceResult,
    LocalCitationPersistenceResult,
)
from mneme.services.semantic_scholar import CitationDirection, SemanticPaper


def _paper(*, arxiv_id: str = "2401.00001", semantic_id: str | None = None) -> Paper:
    return Paper(
        id=uuid4(),
        arxiv_id=arxiv_id,
        semantic_scholar_id=semantic_id,
        title="Paper",
        abstract="Abstract",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )


def _collection(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = values
    return result


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_reference_rows_are_deduplicated_and_use_external_targets() -> None:
    async def exercise() -> tuple[AsyncMock, Insert]:
        session = AsyncMock(spec=AsyncSession)
        center = _paper()
        session.scalar.return_value = center
        session.scalars.side_effect = [
            _collection([]),
            _collection([]),
            _collection([]),
        ]
        inserted = MagicMock()
        inserted.scalars.return_value.all.return_value = [uuid4()]
        session.execute.return_value = inserted
        neighbor = SemanticPaper(paperId="s2-neighbor", externalIds=None)

        result = await CitationGraphRepository().persist_neighbors(
            cast(AsyncSession, session),
            center_paper_id=center.id,
            center_semantic_scholar_id="s2-center",
            direction=CitationDirection.REFERENCES,
            neighbors=(neighbor, neighbor),
        )
        assert result is not None
        assert (result.observed, result.inserted, result.duplicates) == (2, 1, 1)
        return session, cast(Insert, session.execute.await_args.args[0])

    session, statement = asyncio.run(exercise())
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT DO NOTHING" in str(compiled)
    assert compiled.params["source_paper_id_m0"] is not None
    assert compiled.params["external_source_id_m0"] is None
    assert compiled.params["target_paper_id_m0"] is None
    assert compiled.params["external_target_id_m0"] == "s2-neighbor"
    assert session.flush.await_count == 2


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_citation_rows_use_external_sources_and_skip_provider_self_edges() -> None:
    async def exercise() -> tuple[CitationPersistenceResult, Insert]:
        session = AsyncMock(spec=AsyncSession)
        center = _paper(semantic_id="s2-center")
        session.scalar.return_value = center
        session.scalars.side_effect = [
            _collection([]),
            _collection([]),
            _collection([]),
        ]
        inserted = MagicMock()
        inserted.scalars.return_value.all.return_value = [uuid4()]
        session.execute.return_value = inserted

        result = await CitationGraphRepository().persist_neighbors(
            cast(AsyncSession, session),
            center_paper_id=center.id,
            center_semantic_scholar_id="s2-center",
            direction=CitationDirection.CITATIONS,
            neighbors=(
                SemanticPaper(paperId="s2-citing"),
                SemanticPaper(paperId="s2-center"),
            ),
        )
        assert result is not None
        return result, cast(Insert, session.execute.await_args.args[0])

    result, statement = asyncio.run(exercise())
    assert (result.inserted, result.skipped_self) == (1, 1)
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params["source_paper_id_m0"] is None
    assert compiled.params["external_source_id_m0"] == "s2-citing"
    assert compiled.params["target_paper_id_m0"] is not None


@pytest.mark.base
@pytest.mark.db
def test_identity_conflicts_are_never_silently_overwritten() -> None:
    paper = _paper(semantic_id="existing")
    with pytest.raises(CitationIdentityConflict, match="different"):
        CitationGraphRepository._assign_identity(paper, "incoming")


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_local_arxiv_edges_are_directed_idempotent_and_do_not_assign_provider_ids() -> None:
    async def exercise() -> tuple[
        AsyncMock,
        LocalCitationPersistenceResult,
        Insert,
        str,
    ]:
        session = AsyncMock(spec=AsyncSession)
        center = _paper(arxiv_id="1706.03762")
        reference = _paper(arxiv_id="1810.04805")
        citation = _paper(arxiv_id="2005.14165")
        session.scalars.return_value = _collection([center, reference, citation])
        inserted = MagicMock()
        inserted.scalars.return_value.all.return_value = [uuid4(), uuid4()]
        session.execute.side_effect = [inserted, MagicMock(), MagicMock()]

        result = await CitationGraphRepository().persist_local_arxiv_edges(
            cast(AsyncSession, session),
            center_paper_id=center.id,
            reference_arxiv_ids=(reference.arxiv_id,),
            citation_arxiv_ids=(citation.arxiv_id,),
            evidence_source="openalex",
        )
        assert result is not None
        return (
            session,
            result,
            cast(Insert, session.execute.await_args_list[0].args[0]),
            str(session.scalars.await_args.args[0].compile(dialect=postgresql.dialect())),
        )

    session, result, statement, lock_sql = asyncio.run(exercise())
    assert (result.observed, result.inserted, result.duplicates) == (2, 2, 0)
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params["source_paper_id_m0"] != compiled.params["target_paper_id_m0"]
    assert compiled.params["source_paper_id_m1"] != compiled.params["target_paper_id_m1"]
    metadata = (
        compiled.params["algorithm_metadata_m0"],
        compiled.params["algorithm_metadata_m1"],
    )
    assert all(value["evidence_source"] == "openalex" for value in metadata)
    assert all(
        value.get(GRAPH_PREPARED_AS_SOURCE) is True or value.get(GRAPH_PREPARED_AS_TARGET) is True
        for value in metadata
    )
    assert "ORDER BY papers.id" in lock_sql
    assert "FOR UPDATE" in lock_sql
    marker_updates = [
        call.args[0].compile(dialect=postgresql.dialect()).params
        for call in session.execute.await_args_list[1:]
    ]
    assert all(
        any(
            value
            in (
                {GRAPH_PREPARED_AS_SOURCE: True},
                {GRAPH_PREPARED_AS_TARGET: True},
            )
            for value in parameters.values()
        )
        for parameters in marker_updates
    )
    assert session.flush.await_count == 0


@pytest.mark.base
@pytest.mark.db
def test_resolution_merges_algorithm_data_before_removing_collision() -> None:
    async def exercise() -> tuple[AsyncMock, Citation]:
        session = AsyncMock(spec=AsyncSession)
        paper = _paper(semantic_id="s2-target")
        source_id = uuid4()
        unresolved = Citation(
            source_paper_id=source_id,
            external_target_id="s2-target",
            algorithm_weight=0.4,
            algorithm_metadata={"provider": "s2"},
        )
        existing = Citation(
            source_paper_id=source_id,
            target_paper_id=paper.id,
            algorithm_weight=None,
            algorithm_metadata={"version": "v1"},
        )
        session.scalars.side_effect = [
            _collection([unresolved]),
            _collection([]),
        ]
        session.scalar.return_value = existing

        count = await CitationGraphRepository()._resolve_existing_edges(
            cast(AsyncSession, session), paper
        )
        assert count == 1
        return session, existing

    session, existing = asyncio.run(exercise())
    session.delete.assert_awaited_once()
    assert existing.algorithm_weight == 0.4
    assert existing.algorithm_metadata == {"provider": "s2", "version": "v1"}
