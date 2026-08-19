"""Single-paper retrieval: embed the query, ANN-search stored chunks."""

from typing import Any, Protocol
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.embeddings import EmbeddingService

logger = structlog.get_logger(__name__)

DEFAULT_CONTEXT_ANCHOR_COUNT = 2


class SupportsChunkSearch(Protocol):
    """The ANN-search surface retrieval needs from the artifact repository."""

    async def search_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[Any, float]]:
        """Return (chunk row, cosine similarity) pairs, best first."""
        ...

    async def get_context_anchor_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[Any, float]]:
        """Return early document chunks that preserve overview context."""
        ...


class RetrievedChunk(BaseModel):
    """One evidence chunk with provenance and its similarity score.

    ``is_dense_result`` and ``is_context_anchor`` are independent: an early
    document chunk can be both a dense top-k hit and an overview anchor.
    Retrieval-quality metrics must grade on ``is_dense_result``; treating
    "anchor" as "not dense" turns such dual hits into false misses.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    paper_id: UUID
    chunk_index: int = Field(ge=0)
    section_title: str | None
    content: str
    page_start: int | None = None
    page_end: int | None = None
    score: float = Field(ge=0, le=1)
    is_dense_result: bool = True
    is_context_anchor: bool = False


class RetrievalService:
    """Top-k chunk retrieval for one paper via pgvector ANN search."""

    def __init__(
        self,
        *,
        embedder: EmbeddingService,
        artifacts: SupportsChunkSearch,
        top_k: int,
        context_anchor_count: int = DEFAULT_CONTEXT_ANCHOR_COUNT,
    ) -> None:
        if context_anchor_count < 0:
            raise ValueError("context_anchor_count must not be negative")
        self._embedder = embedder
        self._artifacts = artifacts
        self._top_k = top_k
        self._context_anchor_count = context_anchor_count

    async def retrieve(
        self, *, paper_id: UUID, paper_version_id: UUID, question: str
    ) -> list[RetrievedChunk]:
        """Return one revision's most similar embedded chunks for a question."""
        query_embedding = await self._embedder.embed_query(question)
        rows = await self._artifacts.search_chunks(
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            query_embedding=query_embedding,
            limit=self._top_k,
        )
        anchor_rows = (
            await self._artifacts.get_context_anchor_chunks(
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                query_embedding=query_embedding,
                limit=self._context_anchor_count,
            )
            if self._context_anchor_count
            else []
        )
        anchor_ids = {chunk.id for chunk, _score in anchor_rows}
        dense_ids = {chunk.id for chunk, _score in rows}
        combined_rows = [*rows, *(row for row in anchor_rows if row[0].id not in dense_ids)]
        results = [
            RetrievedChunk(
                chunk_id=chunk.id,
                paper_id=chunk.paper_id,
                chunk_index=chunk.chunk_index,
                section_title=chunk.section_title,
                content=chunk.content,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=score,
                is_dense_result=chunk.id in dense_ids,
                is_context_anchor=chunk.id in anchor_ids,
            )
            for chunk, score in combined_rows
        ]
        logger.info(
            "retrieval_completed",
            paper_id=str(paper_id),
            paper_version_id=str(paper_version_id),
            chunks=len(results),
            dense_chunks=len(rows),
            context_anchors=len(anchor_ids),
            top_score=results[0].score if results else None,
        )
        return results
