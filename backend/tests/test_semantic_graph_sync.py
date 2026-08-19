"""Tests for two-direction Semantic Scholar graph synchronization."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mneme.repositories.citation_graph import (
    CitationGraphRepository,
    CitationPersistenceResult,
)
from mneme.services.semantic_scholar import (
    CitationDirection,
    SemanticPaper,
    SemanticScholarClient,
)
from mneme.services.semantic_scholar.sync import (
    SemanticGraphSyncService,
    SemanticGraphTargetNotFound,
)


def _session_context(session: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def _result(*, inserted: int) -> CitationPersistenceResult:
    return CitationPersistenceResult(2, inserted, 2 - inserted, 0, 0)


@pytest.mark.base
@pytest.mark.pipeline
def test_sync_fetches_outside_transaction_and_persists_both_directions() -> None:
    async def exercise() -> tuple[MagicMock, AsyncMock, AsyncMock]:
        paper_id = uuid4()
        read_session = AsyncMock(spec=AsyncSession)
        target_result = MagicMock()
        target_result.one_or_none.return_value = (paper_id, "2401.00001")
        read_session.execute.return_value = target_result

        write_session = AsyncMock(spec=AsyncSession)
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=None)
        write_session.begin.return_value = transaction
        factory = MagicMock(
            side_effect=[_session_context(read_session), _session_context(write_session)]
        )

        client = MagicMock(spec=SemanticScholarClient)
        center = SemanticPaper(paperId="s2-center", externalIds={"ArXiv": "2401.00001v3"})
        client.fetch_papers = AsyncMock(return_value=(center,))
        client.fetch_neighbors = AsyncMock(
            side_effect=[
                (SemanticPaper(paperId="reference"),),
                (SemanticPaper(paperId="citation"),),
            ]
        )
        repository = MagicMock(spec=CitationGraphRepository)
        repository.persist_neighbors = AsyncMock(
            side_effect=[_result(inserted=1), _result(inserted=2)]
        )

        summary = await SemanticGraphSyncService(
            cast(async_sessionmaker[AsyncSession], factory),
            cast(SemanticScholarClient, client),
            cast(CitationGraphRepository, repository),
        ).sync(paper_id=paper_id, limit=10)

        assert summary.paper_id == paper_id
        assert summary.semantic_scholar_id == "s2-center"
        assert summary.references.inserted == 1
        assert summary.citations.inserted == 2
        return factory, client.fetch_neighbors, repository.persist_neighbors

    factory, fetch_neighbors, persist_neighbors = asyncio.run(exercise())
    assert factory.call_count == 2
    assert [call.args[1] for call in fetch_neighbors.await_args_list] == [
        CitationDirection.REFERENCES,
        CitationDirection.CITATIONS,
    ]
    assert [call.kwargs["direction"] for call in persist_neighbors.await_args_list] == [
        CitationDirection.REFERENCES,
        CitationDirection.CITATIONS,
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_sync_rejects_missing_or_mismatched_targets() -> None:
    async def missing_local() -> None:
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.one_or_none.return_value = None
        session.execute.return_value = result
        factory = MagicMock(return_value=_session_context(session))
        service = SemanticGraphSyncService(
            cast(async_sessionmaker[AsyncSession], factory),
            cast(SemanticScholarClient, MagicMock(spec=SemanticScholarClient)),
        )
        with pytest.raises(SemanticGraphTargetNotFound, match="local"):
            await service.sync(arxiv_id="missing", limit=1)

    asyncio.run(missing_local())

    with pytest.raises(SemanticGraphTargetNotFound, match="no matching"):
        SemanticGraphSyncService._select_center(
            (SemanticPaper(paperId="other", externalIds={"ArXiv": "2401.99999"}),),
            "2401.00001",
        )
    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(
            SemanticGraphSyncService(
                cast(async_sessionmaker[AsyncSession], MagicMock()),
                cast(SemanticScholarClient, MagicMock()),
            ).sync(limit=1)
        )
