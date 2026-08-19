"""Tests for citation-backed seed onboarding candidates."""

import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.repositories.citation_graph import (
    CitationGraphRepository,
    CitationPersistenceResult,
)
from mneme.services.arxiv.client import ArxivClient, ArxivHTTPError
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivFeed, ArxivPaperRecord
from mneme.services.seed_graph import (
    InsufficientSeedGraphCandidates,
    SeedGraphCandidateService,
    SeedGraphMetadataUnavailable,
)
from mneme.services.semantic_scholar import (
    CitationDirection,
    SemanticPaper,
    SemanticScholarClient,
)

SEED_ID = "1706.03762"


def _record(arxiv_id: str) -> ArxivPaperRecord:
    timestamp = datetime(2020, 1, 1, tzinfo=UTC)
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=1,
        title=f"Paper {arxiv_id}",
        abstract="Abstract",
        authors=(ArxivAuthorRecord(name="Author"),),
        categories=("cs.AI",),
        primary_category="cs.AI",
        published_at=timestamp,
        updated_at=timestamp,
        abstract_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        source_license=None,
        doi=None,
        comment=None,
        journal_reference=None,
    )


def _feed(*arxiv_ids: str) -> ArxivFeed:
    return ArxivFeed(
        records=tuple(_record(arxiv_id) for arxiv_id in reversed(arxiv_ids)),
        total_results=len(arxiv_ids),
        start_index=0,
        items_per_page=len(arxiv_ids),
    )


def _provider(arxiv_id: str | None, *, paper_id: str) -> SemanticPaper:
    external_ids = {"ArXiv": arxiv_id} if arxiv_id is not None else None
    return SemanticPaper(paperId=paper_id, externalIds=external_ids)


@pytest.mark.base
@pytest.mark.pipeline
def test_discovery_returns_five_arxiv_records_in_provider_order() -> None:
    async def exercise():
        arxiv = MagicMock(spec=ArxivClient)
        arxiv.fetch_by_ids = AsyncMock(
            return_value=_feed("1705.00001", "1705.00002", "1705.00003", "1705.00004", "1705.00005")
        )
        semantic = MagicMock(spec=SemanticScholarClient)
        semantic.fetch_paper_references = AsyncMock(
            return_value=(
                _provider(SEED_ID, paper_id="s2-seed"),
                (
                    _provider("1705.00001", paper_id="ref-1"),
                    _provider("1705.00002", paper_id="ref-2"),
                    _provider(None, paper_id="no-arxiv"),
                    _provider(SEED_ID, paper_id="self"),
                    _provider("1705.00002", paper_id="duplicate"),
                    _provider("1705.00003", paper_id="cite-3"),
                    _provider("1705.00004", paper_id="cite-4"),
                    _provider("1705.00005", paper_id="cite-5"),
                ),
            )
        )
        semantic.fetch_neighbors = AsyncMock(return_value=())

        result = await SeedGraphCandidateService(
            cast(ArxivClient, arxiv),
            cast(SemanticScholarClient, semantic),
        ).discover(SEED_ID, library_size=5, neighbor_limit=10)
        return result, arxiv, semantic

    result, arxiv, semantic = asyncio.run(exercise())
    assert [record.arxiv_id for record in result.feed.records] == [
        "1705.00001",
        "1705.00002",
        "1705.00003",
        "1705.00004",
        "1705.00005",
    ]
    arxiv.fetch_by_ids.assert_awaited_once_with(
        (
            "1705.00001",
            "1705.00002",
            "1705.00003",
            "1705.00004",
            "1705.00005",
        )
    )
    semantic.fetch_neighbors.assert_not_awaited()


@pytest.mark.base
@pytest.mark.pipeline
@pytest.mark.parametrize(
    "batch_error",
    [ArxivHTTPError(429), ValueError("configured batch is smaller than the library")],
)
def test_discovery_recovers_failed_batch_with_single_requests(
    batch_error: Exception,
) -> None:
    candidate_ids = tuple(f"1705.0000{index}" for index in range(1, 6))

    async def exercise():
        arxiv = MagicMock(spec=ArxivClient)
        arxiv.fetch_by_ids = AsyncMock(
            side_effect=[
                batch_error,
                *(_feed(arxiv_id) for arxiv_id in candidate_ids),
            ]
        )
        semantic = MagicMock(spec=SemanticScholarClient)
        semantic.fetch_paper_references = AsyncMock(
            return_value=(
                _provider(SEED_ID, paper_id="s2-seed"),
                tuple(
                    _provider(arxiv_id, paper_id=f"ref-{index}")
                    for index, arxiv_id in enumerate(candidate_ids, start=1)
                ),
            )
        )
        semantic.fetch_neighbors = AsyncMock(return_value=())

        result = await SeedGraphCandidateService(
            cast(ArxivClient, arxiv),
            cast(SemanticScholarClient, semantic),
        ).discover(SEED_ID, library_size=5, neighbor_limit=10)
        return result, arxiv

    result, arxiv = asyncio.run(exercise())
    assert [record.arxiv_id for record in result.feed.records] == list(candidate_ids)
    assert arxiv.fetch_by_ids.await_args_list == [
        call(candidate_ids),
        *(call((arxiv_id,)) for arxiv_id in candidate_ids),
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_discovery_uses_later_neighbor_after_one_single_request_fails() -> None:
    candidate_ids = tuple(f"1705.0000{index}" for index in range(1, 7))

    async def exercise():
        arxiv = MagicMock(spec=ArxivClient)
        arxiv.fetch_by_ids = AsyncMock(
            side_effect=[
                ArxivHTTPError(429),
                ArxivHTTPError(429),
                *(_feed(arxiv_id) for arxiv_id in candidate_ids[1:5]),
                _feed(candidate_ids[5]),
            ]
        )
        semantic = MagicMock(spec=SemanticScholarClient)
        semantic.fetch_paper_references = AsyncMock(
            return_value=(
                _provider(SEED_ID, paper_id="s2-seed"),
                tuple(
                    _provider(arxiv_id, paper_id=f"ref-{index}")
                    for index, arxiv_id in enumerate(candidate_ids, start=1)
                ),
            )
        )
        semantic.fetch_neighbors = AsyncMock(return_value=())

        result = await SeedGraphCandidateService(
            cast(ArxivClient, arxiv),
            cast(SemanticScholarClient, semantic),
        ).discover(SEED_ID, library_size=5, neighbor_limit=10)
        return result, arxiv

    result, arxiv = asyncio.run(exercise())
    assert [record.arxiv_id for record in result.feed.records] == list(candidate_ids[1:])
    assert arxiv.fetch_by_ids.await_args_list == [
        call(candidate_ids[:5]),
        *(call((arxiv_id,)) for arxiv_id in candidate_ids[:5]),
        call((candidate_ids[5],)),
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_discovery_fails_explicitly_when_neighbor_metadata_remains_unavailable() -> None:
    candidate_ids = tuple(f"1705.0000{index}" for index in range(1, 6))

    async def exercise() -> None:
        arxiv = MagicMock(spec=ArxivClient)
        arxiv.fetch_by_ids = AsyncMock(side_effect=ArxivHTTPError(429))
        semantic = MagicMock(spec=SemanticScholarClient)
        semantic.fetch_paper_references = AsyncMock(
            return_value=(
                _provider(SEED_ID, paper_id="s2-seed"),
                tuple(
                    _provider(arxiv_id, paper_id=f"ref-{index}")
                    for index, arxiv_id in enumerate(candidate_ids, start=1)
                ),
            )
        )
        semantic.fetch_neighbors = AsyncMock(return_value=())

        service = SeedGraphCandidateService(
            cast(ArxivClient, arxiv),
            cast(SemanticScholarClient, semantic),
        )
        with pytest.raises(SeedGraphMetadataUnavailable, match="remained unavailable"):
            await service.discover(SEED_ID, library_size=5, neighbor_limit=10)

    asyncio.run(exercise())


@pytest.mark.base
@pytest.mark.pipeline
def test_discovery_rejects_missing_center_and_incomplete_arxiv_results() -> None:
    arxiv = MagicMock(spec=ArxivClient)
    semantic = MagicMock(spec=SemanticScholarClient)
    semantic.fetch_paper_references = AsyncMock(
        return_value=(_provider("1706.00000", paper_id="wrong"), ())
    )
    service = SeedGraphCandidateService(
        cast(ArxivClient, arxiv),
        cast(SemanticScholarClient, semantic),
    )
    with pytest.raises(InsufficientSeedGraphCandidates, match="matching"):
        asyncio.run(service.discover(SEED_ID, library_size=5, neighbor_limit=10))

    semantic.fetch_paper_references = AsyncMock(
        return_value=(
            _provider(SEED_ID, paper_id="s2-seed"),
            tuple(_provider(f"1705.0000{index}", paper_id=f"ref-{index}") for index in range(1, 6)),
        )
    )
    semantic.fetch_neighbors = AsyncMock(return_value=())
    arxiv.fetch_by_ids = AsyncMock(return_value=_feed("1705.00001"))
    with pytest.raises(InsufficientSeedGraphCandidates, match="enough"):
        asyncio.run(service.discover(SEED_ID, library_size=5, neighbor_limit=10))


@pytest.mark.base
@pytest.mark.pipeline
def test_general_neighborhood_fetches_both_citation_directions() -> None:
    arxiv = cast(ArxivClient, MagicMock(spec=ArxivClient))
    semantic = MagicMock(spec=SemanticScholarClient)
    reference = _provider("1705.00001", paper_id="reference")
    citation = _provider("1705.00002", paper_id="citation")
    semantic.fetch_paper_references = AsyncMock(
        return_value=(_provider(SEED_ID, paper_id="center"), (reference,))
    )
    semantic.fetch_neighbors = AsyncMock(return_value=(citation,))
    service = SeedGraphCandidateService(arxiv, cast(SemanticScholarClient, semantic))

    result = asyncio.run(service.discover_neighborhood(SEED_ID, neighbor_limit=20))

    assert result.references == (reference,)
    assert result.citations == (citation,)
    semantic.fetch_neighbors.assert_awaited_once_with(
        "center",
        CitationDirection.CITATIONS,
        limit=20,
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_general_metadata_resolution_retains_a_real_partial_batch() -> None:
    arxiv = MagicMock(spec=ArxivClient)
    arxiv.fetch_by_ids = AsyncMock(return_value=_feed("1705.00001"))
    semantic = cast(SemanticScholarClient, MagicMock(spec=SemanticScholarClient))
    service = SeedGraphCandidateService(cast(ArxivClient, arxiv), semantic)

    result = asyncio.run(
        service.resolve_available_arxiv_records(
            ("1705.00001", "1705.00002"),
            limit=2,
        )
    )

    assert tuple(record.arxiv_id for record in result) == ("1705.00001",)
    arxiv.fetch_by_ids.assert_awaited_once_with(("1705.00001", "1705.00002"))


@pytest.mark.base
@pytest.mark.db
@pytest.mark.pipeline
def test_persistence_writes_both_directions_in_one_transaction() -> None:
    async def exercise():
        arxiv = cast(ArxivClient, MagicMock(spec=ArxivClient))
        semantic = cast(SemanticScholarClient, MagicMock(spec=SemanticScholarClient))
        repository = MagicMock(spec=CitationGraphRepository)
        repository.persist_neighbors = AsyncMock(
            side_effect=[
                CitationPersistenceResult(5, 5, 0, 5, 0),
                CitationPersistenceResult(2, 2, 0, 2, 0),
            ]
        )
        service = SeedGraphCandidateService(arxiv, semantic, repository)
        candidates = MagicMock()
        candidates.center.paper_id = "s2-seed"
        candidates.references = tuple(
            _provider(f"1705.0000{index}", paper_id=f"ref-{index}") for index in range(1, 6)
        )
        candidates.citations = ()
        session = AsyncMock(spec=AsyncSession)
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=None)
        session.begin.return_value = transaction

        result = await service.persist(
            cast(AsyncSession, session),
            center_paper_id=uuid4(),
            candidates=candidates,
        )
        return result, repository, transaction

    result, repository, transaction = asyncio.run(exercise())
    assert result.references.inserted == 5
    assert result.citations.inserted == 2
    assert [call.kwargs["direction"] for call in repository.persist_neighbors.await_args_list] == [
        CitationDirection.REFERENCES,
        CitationDirection.CITATIONS,
    ]
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()
