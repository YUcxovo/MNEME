"""Single-paper retrieval: embed the query, ANN-search stored chunks."""

from typing import Any, Protocol
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.embeddings import EmbeddingService

logger = structlog.get_logger(__name__)


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


class RetrievedChunk(BaseModel):
    """One evidence chunk with provenance and its similarity score."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    paper_id: UUID
    chunk_index: int = Field(ge=0)
    section_title: str | None
    content: str
    page_start: int | None = None
    page_end: int | None = None
    score: float = Field(ge=0, le=1)


class RetrievalService:
    """Top-k chunk retrieval for one paper via pgvector ANN search."""

    def __init__(
        self,
        *,
        embedder: EmbeddingService,
        artifacts: SupportsChunkSearch,
        top_k: int,
    ) -> None:
        self._embedder = embedder
        self._artifacts = artifacts
        self._top_k = top_k

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
            )
            for chunk, score in rows
        ]
        logger.info(
            "retrieval_completed",
            paper_id=str(paper_id),
            paper_version_id=str(paper_version_id),
            chunks=len(results),
            top_score=results[0].score if results else None,
        )
        return results
