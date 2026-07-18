"""Persistence for recommendation candidates and generated digests."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mneme.models.artifact import PaperChunk
from mneme.models.base import utc_now
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.paper import Paper, PaperAuthor
from mneme.models.user import UserPreference


class DigestRepository:
    """Build and fetch research briefings through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preferences(self, user_id: UUID) -> UserPreference | None:
        """Return the stored preference row for scoring."""
        return await self._session.get(UserPreference, user_id)

    async def list_recent_candidates(self, *, since: datetime, limit: int) -> list[Paper]:
        """Return recent papers with authors eagerly loaded for responses."""
        statement = (
            select(Paper)
            .where(Paper.published_at >= since)
            .order_by(Paper.published_at.desc(), Paper.id.desc())
            .limit(limit)
            .options(selectinload(Paper.author_links).selectinload(PaperAuthor.author))
        )
        return list((await self._session.scalars(statement)).all())

    async def mean_chunk_embeddings(self, paper_ids: list[UUID]) -> dict[UUID, tuple[float, ...]]:
        """Return each paper's mean chunk embedding, where one exists."""
        if not paper_ids:
            return {}
        statement = (
            select(PaperChunk.paper_id, func.avg(PaperChunk.embedding).label("embedding"))
            .where(PaperChunk.paper_id.in_(paper_ids), PaperChunk.embedding.is_not(None))
            .group_by(PaperChunk.paper_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: tuple(row[1]) for row in rows if row[1] is not None}

    async def get_fresh_recommended_digest(
        self, *, user_id: UUID, max_age: timedelta
    ) -> Digest | None:
        """Return the newest manual digest if it is still fresh."""
        statement = (
            select(Digest)
            .where(
                Digest.user_id == user_id,
                Digest.digest_type == DigestType.MANUAL,
                Digest.generated_at >= utc_now() - max_age,
            )
            .order_by(Digest.generated_at.desc())
            .limit(1)
            .options(
                selectinload(Digest.entries)
                .selectinload(DigestEntry.paper)
                .selectinload(Paper.author_links)
                .selectinload(PaperAuthor.author)
            )
        )
        return await self._session.scalar(statement)

    async def create_digest(
        self,
        *,
        user_id: UUID,
        digest_type: DigestType,
        preference_model_version: int,
        generator_version: str,
        entries: list[DigestEntry],
    ) -> Digest:
        """Persist one immutable digest snapshot with its ranked entries."""
        digest = Digest(
            user_id=user_id,
            digest_type=digest_type,
            preference_model_version=preference_model_version,
            generator_version=generator_version,
        )
        self._session.add(digest)
        await self._session.flush()
        for entry in entries:
            entry.digest_id = digest.id
            self._session.add(entry)
        await self._session.flush()
        return digest
