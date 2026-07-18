"""Persistence for generated artifacts: chunks, embeddings, and summaries."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.chunking import ChunkDraft
from mneme.models.artifact import PaperChunk, PaperSummary
from mneme.models.paper import PaperVersion


@dataclass(frozen=True, slots=True)
class ChunkEmbeddingUpdate:
    """One vector to attach to an existing chunk."""

    chunk_id: UUID
    embedding: tuple[float, ...]
    embedding_model: str


class ArtifactRepository:
    """Store and query per-revision artifacts through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_version(self, paper_id: UUID) -> PaperVersion | None:
        """Return the newest observed revision of one paper."""
        statement = (
            select(PaperVersion)
            .where(PaperVersion.paper_id == paper_id)
            .order_by(PaperVersion.version_number.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def replace_chunks(
        self, *, paper_id: UUID, paper_version_id: UUID, drafts: list[ChunkDraft]
    ) -> list[PaperChunk]:
        """Idempotently replace all chunks for one revision."""
        await self._session.execute(
            delete(PaperChunk).where(PaperChunk.paper_version_id == paper_version_id)
        )
        chunks = [
            PaperChunk(
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                section_title=draft.section_title,
                chunk_index=draft.chunk_index,
                page_start=draft.page_start,
                page_end=draft.page_end,
                content=draft.content,
                content_hash=draft.content_hash,
                token_count=draft.token_count,
            )
            for draft in drafts
        ]
        self._session.add_all(chunks)
        await self._session.flush()
        return chunks

    async def list_chunks_without_embedding(
        self, *, paper_version_id: UUID, limit: int
    ) -> list[PaperChunk]:
        """Return unembedded chunks for one revision in chunk order."""
        statement = (
            select(PaperChunk)
            .where(
                PaperChunk.paper_version_id == paper_version_id,
                PaperChunk.embedding.is_(None),
            )
            .order_by(PaperChunk.chunk_index)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def set_chunk_embeddings(self, updates: list[ChunkEmbeddingUpdate]) -> None:
        """Attach vectors to previously stored chunks."""
        for item in updates:
            await self._session.execute(
                update(PaperChunk)
                .where(PaperChunk.id == item.chunk_id)
                .values(embedding=list(item.embedding), embedding_model=item.embedding_model)
            )
        await self._session.flush()

    async def find_summary_by_input(
        self, *, paper_version_id: UUID, input_hash: str, prompt_version: str
    ) -> PaperSummary | None:
        """Return a stored summary for one exact input, any provider/model.

        Used for idempotency: an existing summary of the same input under the
        same prompt version makes regeneration unnecessary.
        """
        statement = (
            select(PaperSummary)
            .where(
                PaperSummary.paper_version_id == paper_version_id,
                PaperSummary.input_hash == input_hash,
                PaperSummary.prompt_version == prompt_version,
            )
            .order_by(PaperSummary.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def get_latest_summary(self, paper_id: UUID) -> PaperSummary | None:
        """Return the most recently generated summary for one paper."""
        statement = (
            select(PaperSummary)
            .where(PaperSummary.paper_id == paper_id)
            .order_by(PaperSummary.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def add_summary(self, summary: PaperSummary) -> PaperSummary:
        """Persist one generated summary."""
        self._session.add(summary)
        await self._session.flush()
        return summary

    async def search_chunks(
        self, *, paper_id: UUID, query_embedding: tuple[float, ...], limit: int
    ) -> list[tuple[PaperChunk, float]]:
        """Return the nearest embedded chunks of one paper with similarity.

        Uses pgvector cosine distance; the returned score is cosine
        similarity in [0, 1] (1 = identical direction).
        """
        distance = PaperChunk.embedding.cosine_distance(list(query_embedding))
        statement = (
            select(PaperChunk, distance.label("distance"))
            .where(PaperChunk.paper_id == paper_id, PaperChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [(row[0], max(0.0, 1.0 - float(row[1]))) for row in rows]
