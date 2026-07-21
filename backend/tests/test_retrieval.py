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

    def __init__(self, rows: list[tuple[FakeChunk, float]]) -> None:
        self.rows = rows
        self.queries: list[tuple[UUID, UUID, tuple[float, ...], int]] = []

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
