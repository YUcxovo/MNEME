"""Retrieval pipeline: query embedding plus ANN search plumbing."""

import asyncio
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from conftest import FakeRedis
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.embeddings import EmbeddingService, FakeEmbeddingProvider
from mneme.ai.retrieval import RetrievalService

PAPER_ID = uuid4()
PAPER_VERSION_ID = uuid4()


class FakeChunk:
    """Duck-typed PaperChunk row."""

    def __init__(self, index: int, content: str) -> None:
        self.id = uuid4()
        self.paper_id = PAPER_ID
        self.chunk_index = index
        self.section_title = f"Section {index}"
        self.content = content
        self.page_start = 1
        self.page_end = 2


class FakeArtifactRepository:
    """Records the ANN query and returns scripted scored chunks."""

    def __init__(
        self,
        rows: list[tuple[FakeChunk, float]],
        *,
        anchors: list[tuple[FakeChunk, float]] | None = None,
    ) -> None:
        self.rows = rows
        self.anchors = anchors if anchors is not None else rows[:2]
        self.queries: list[tuple[UUID, UUID, tuple[float, ...], int]] = []
        self.anchor_queries: list[tuple[UUID, UUID, tuple[float, ...], int]] = []

    async def search_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[FakeChunk, float]]:
        self.queries.append((paper_id, paper_version_id, query_embedding, limit))
        return self.rows[:limit]

    async def get_context_anchor_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[FakeChunk, float]]:
        self.anchor_queries.append((paper_id, paper_version_id, query_embedding, limit))
        return self.anchors[:limit]


def _embedder(fake_redis: FakeRedis) -> EmbeddingService:
    return EmbeddingService(
        provider=FakeEmbeddingProvider(),
        budget=BudgetGuard(cast(Redis, fake_redis), daily_cap_usd=Decimal("5")),
        model="text-embedding-3-small",
        batch_size=8,
    )


@pytest.mark.base
@pytest.mark.rag
def test_retrieve_returns_top_k_chunks_with_metadata(fake_redis: FakeRedis) -> None:
    rows = [(FakeChunk(index, f"content {index}"), 0.9 - index * 0.1) for index in range(3)]
    repository = FakeArtifactRepository(rows)
    service = RetrievalService(embedder=_embedder(fake_redis), artifacts=repository, top_k=2)

    results = asyncio.run(
        service.retrieve(
            paper_id=PAPER_ID,
            paper_version_id=PAPER_VERSION_ID,
            question="what is this?",
        )
    )

    assert len(results) == 2
    assert results[0].score == pytest.approx(0.9)
    assert results[0].section_title == "Section 0"
    assert results[0].paper_id == PAPER_ID
    paper_id, paper_version_id, embedding, limit = repository.queries[0]
    assert paper_id == PAPER_ID
    assert paper_version_id == PAPER_VERSION_ID
    assert len(embedding) == 8
    assert limit == 2
    assert repository.anchor_queries[0][3] == 2


@pytest.mark.base
@pytest.mark.rag
def test_retrieve_appends_overview_anchors_without_displacing_dense_hits(
    fake_redis: FakeRedis,
) -> None:
    dense = [(FakeChunk(8, "specific result"), 0.9), (FakeChunk(9, "specific method"), 0.8)]
    anchors = [(FakeChunk(0, "paper abstract"), 0.4), (FakeChunk(1, "introduction"), 0.3)]
    service = RetrievalService(
        embedder=_embedder(fake_redis),
        artifacts=FakeArtifactRepository(dense, anchors=anchors),
        top_k=2,
    )

    results = asyncio.run(
        service.retrieve(
            paper_id=PAPER_ID,
            paper_version_id=PAPER_VERSION_ID,
            question="what problem does the paper address?",
        )
    )

    assert [result.chunk_index for result in results] == [8, 9, 0, 1]
    assert [result.is_dense_result for result in results] == [True, True, False, False]
    assert [result.is_context_anchor for result in results] == [False, False, True, True]


@pytest.mark.base
@pytest.mark.rag
def test_retrieve_keeps_dense_membership_when_a_chunk_is_also_an_anchor(
    fake_redis: FakeRedis,
) -> None:
    """Regression: a chunk in both result sets stayed marked anchor-only,
    turning a genuine dense hit into a false recall@k miss downstream."""
    shared = (FakeChunk(0, "overview that also matches the query"), 0.9)
    dense = [shared, (FakeChunk(7, "specific method"), 0.8)]
    anchors = [shared, (FakeChunk(1, "introduction"), 0.3)]
    service = RetrievalService(
        embedder=_embedder(fake_redis),
        artifacts=FakeArtifactRepository(dense, anchors=anchors),
        top_k=2,
    )

    results = asyncio.run(
        service.retrieve(
            paper_id=PAPER_ID,
            paper_version_id=PAPER_VERSION_ID,
            question="what does the paper do?",
        )
    )

    assert [result.chunk_index for result in results] == [0, 7, 1]
    dual = results[0]
    assert dual.is_dense_result is True
    assert dual.is_context_anchor is True
    assert results[2].is_dense_result is False
    assert results[2].is_context_anchor is True


@pytest.mark.base
@pytest.mark.rag
def test_retrieve_handles_papers_without_chunks(fake_redis: FakeRedis) -> None:
    service = RetrievalService(
        embedder=_embedder(fake_redis), artifacts=FakeArtifactRepository([]), top_k=5
    )

    results = asyncio.run(
        service.retrieve(
            paper_id=PAPER_ID,
            paper_version_id=PAPER_VERSION_ID,
            question="anything?",
        )
    )

    assert results == []
