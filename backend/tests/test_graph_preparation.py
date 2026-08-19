"""Orchestration tests for real on-demand citation graph preparation."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mneme.repositories.citation_graph import LocalCitationPersistenceResult
from mneme.repositories.graph_preparation import (
    GraphPreparationRepository,
    GraphPreparationTarget,
    _is_reference_heading,
)
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivPaperRecord
from mneme.services.graph_preparation import GraphPreparationService
from mneme.services.openalex import OpenAlexClient, OpenAlexNeighborhood
from mneme.services.seed_graph import SeedGraphCandidateService, SeedGraphNeighborhood
from mneme.services.semantic_scholar import SemanticPaper, SemanticScholarHTTPError


def _record(arxiv_id: str) -> ArxivPaperRecord:
    now = datetime.now(UTC)
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=1,
        title=f"Paper {arxiv_id}",
        abstract="Abstract",
        authors=(ArxivAuthorRecord(name="Author"),),
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


def _service() -> tuple[
    GraphPreparationService,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    paper_id = uuid4()
    repository = MagicMock(spec=GraphPreparationRepository)
    repository.get_target = AsyncMock(
        return_value=GraphPreparationTarget(
            paper_id=paper_id,
            arxiv_id="1706.03762",
            title="Attention Is All You Need",
        )
    )
    repository.has_prepared_neighborhood = AsyncMock(return_value=False)
    repository.list_reference_chunks = AsyncMock(return_value=())
    repository.persist_candidates = AsyncMock(
        return_value=LocalCitationPersistenceResult(1, 1, 0, 0, 0)
    )
    seed = MagicMock(spec=SeedGraphCandidateService)
    openalex = MagicMock(spec=OpenAlexClient)
    return (
        GraphPreparationService(
            repository,
            MagicMock(spec=ArxivClient),
            seed,
            openalex,
        ),
        repository,
        seed,
        openalex,
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_cached_graph_returns_without_any_upstream_request() -> None:
    service, repository, seed, openalex = _service()
    repository.has_prepared_neighborhood.return_value = True

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.cached
    assert result.evidence_source == "cache"
    seed.discover_neighborhood.assert_not_called()
    openalex.fetch_neighborhood.assert_not_called()


@pytest.mark.base
@pytest.mark.pipeline
def test_semantic_scholar_success_ingests_and_persists_real_directions() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(
        return_value=SeedGraphNeighborhood(
            center=SemanticPaper(
                paperId="s2-center",
                externalIds={"ArXiv": "1706.03762"},
            ),
            references=(
                SemanticPaper(paperId="s2-reference", externalIds={"ArXiv": "1810.04805"}),
            ),
            citations=(SemanticPaper(paperId="s2-citation", externalIds={"ArXiv": "2005.14165"}),),
        )
    )
    seed.resolve_available_arxiv_records = AsyncMock(
        return_value=(_record("1810.04805"), _record("2005.14165"))
    )

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "semantic_scholar"
    call = repository.persist_candidates.await_args.kwargs
    assert call["reference_arxiv_ids"] == ("1810.04805",)
    assert call["citation_arxiv_ids"] == ("2005.14165",)
    openalex.fetch_neighborhood.assert_not_called()


@pytest.mark.base
@pytest.mark.pipeline
def test_semantic_scholar_429_falls_back_to_openalex() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(side_effect=SemanticScholarHTTPError(429))
    openalex.fetch_neighborhood = AsyncMock(
        return_value=OpenAlexNeighborhood(references=("1810.04805",), citations=())
    )
    seed.resolve_available_arxiv_records = AsyncMock(return_value=(_record("1810.04805"),))

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "openalex"
    assert repository.persist_candidates.await_args.kwargs["evidence_source"] == "openalex"


@pytest.mark.base
@pytest.mark.pipeline
def test_semantic_client_limit_validation_also_falls_back_to_openalex() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(
        side_effect=ValueError("Neighbor limit exceeds the configured maximum")
    )
    openalex.fetch_neighborhood = AsyncMock(
        return_value=OpenAlexNeighborhood(references=("1810.04805",), citations=())
    )
    seed.resolve_available_arxiv_records = AsyncMock(return_value=(_record("1810.04805"),))

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "openalex"


@pytest.mark.base
@pytest.mark.pipeline
def test_unindexed_openalex_center_falls_back_to_explicit_parsed_references() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(side_effect=SemanticScholarHTTPError(429))
    openalex.fetch_neighborhood = AsyncMock(return_value=None)
    repository.list_reference_chunks.return_value = (
        "[1] Useful work. arXiv:1810.04805v2. [2] https://arxiv.org/pdf/2005.14165.pdf",
    )
    seed.resolve_available_arxiv_records = AsyncMock(
        return_value=(_record("1810.04805"), _record("2005.14165"))
    )

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "parsed_references"
    call = repository.persist_candidates.await_args.kwargs
    assert call["reference_arxiv_ids"] == ("1810.04805", "2005.14165")
    assert call["citation_arxiv_ids"] == ()


@pytest.mark.base
@pytest.mark.pipeline
def test_absent_provider_and_parsed_evidence_completes_without_synthetic_edges() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(side_effect=SemanticScholarHTTPError(429))
    openalex.fetch_neighborhood = AsyncMock(return_value=None)
    repository.list_reference_chunks.return_value = (
        "A DOI-only reference, unrelated 1810.04805, and notarxiv:2005.14165.",
    )

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "none"
    assert result.resolved_neighbors == 0
    repository.persist_candidates.assert_not_called()


@pytest.mark.base
@pytest.mark.pipeline
def test_parsed_references_reject_tokens_that_only_start_with_a_valid_arxiv_id() -> None:
    service, repository, seed, openalex = _service()
    seed.discover_neighborhood = AsyncMock(side_effect=SemanticScholarHTTPError(429))
    openalex.fetch_neighborhood = AsyncMock(return_value=None)
    repository.list_reference_chunks.return_value = (
        "Invalid arXiv:1810.048051 and arXiv:1810.04805v2extra. "
        "Invalid https://arxiv.org/pdf/2005.14165.pdfx and arXiv:hep-th/9901001extra. "
        "Valid arXiv:2005.14165.",
    )
    seed.resolve_available_arxiv_records = AsyncMock(return_value=(_record("2005.14165"),))

    result = asyncio.run(
        service.prepare(repository.get_target.return_value.paper_id, neighbor_limit=20)
    )

    assert result is not None
    assert result.evidence_source == "parsed_references"
    call = repository.persist_candidates.await_args.kwargs
    assert call["reference_arxiv_ids"] == ("2005.14165",)


@pytest.mark.base
@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("heading", "accepted"),
    [
        ("References", True),
        ("7. References", True),
        ("IX Bibliography:", True),
        ("Works Cited", True),
        ("References and Notes", True),
        ("Cross References", False),
        ("Reference Architecture", False),
        ("Related Work", False),
    ],
)
def test_only_bibliography_heading_variants_are_eligible(heading: str, accepted: bool) -> None:
    assert _is_reference_heading(heading) is accepted


@pytest.mark.base
@pytest.mark.pipeline
def test_repeated_prepare_uses_the_newly_cached_graph() -> None:
    service, repository, seed, _openalex = _service()
    repository.has_prepared_neighborhood.side_effect = [False, True]
    seed.discover_neighborhood = AsyncMock(
        return_value=SeedGraphNeighborhood(
            center=SemanticPaper(paperId="center", externalIds={"ArXiv": "1706.03762"}),
            references=(SemanticPaper(paperId="neighbor", externalIds={"ArXiv": "1810.04805"}),),
            citations=(),
        )
    )
    seed.resolve_available_arxiv_records = AsyncMock(return_value=(_record("1810.04805"),))
    paper_id = repository.get_target.return_value.paper_id

    first = asyncio.run(service.prepare(paper_id, neighbor_limit=20))
    second = asyncio.run(service.prepare(paper_id, neighbor_limit=20))

    assert first is not None and first.evidence_source == "semantic_scholar"
    assert second is not None and second.cached
    assert seed.discover_neighborhood.await_count == 1
    assert repository.persist_candidates.await_count == 1


@pytest.mark.base
@pytest.mark.pipeline
def test_missing_local_paper_never_calls_a_provider() -> None:
    service, repository, seed, openalex = _service()
    repository.get_target.return_value = None

    result = asyncio.run(service.prepare(uuid4(), neighbor_limit=20))

    assert result is None
    repository.has_prepared_neighborhood.assert_not_called()
    seed.discover_neighborhood.assert_not_called()
    openalex.fetch_neighborhood.assert_not_called()
