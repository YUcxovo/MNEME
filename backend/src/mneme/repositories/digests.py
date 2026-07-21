"""Persistence for recommendation candidates and generated digests."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mneme.models.artifact import PaperChunk, PaperSummary
from mneme.models.base import utc_now
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.paper import Paper, PaperAuthor, PaperVersion, ProcessingStatus
from mneme.models.user import UserPreference

_CURSOR_VERSION: Final = 1
_CURSOR_FIELDS: Final = frozenset({"v", "generated_at", "id"})


class InvalidDigestCursorError(ValueError):
    """Raised when an opaque digest cursor is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class DigestCursor:
    """Decoded descending digest-list keyset."""

    generated_at: datetime
    digest_id: UUID


@dataclass(frozen=True, slots=True)
class DigestPageResult:
    """One authenticated digest page plus its optional continuation cursor."""

    items: list[Digest]
    next_cursor: str | None


def encode_digest_cursor(generated_at: datetime, digest_id: UUID) -> str:
    """Encode a stable `(generated_at, id)` keyset as opaque base64url."""
    if generated_at.tzinfo is None:
        raise ValueError("digest cursor timestamps must be timezone-aware")

    payload = {
        "v": _CURSOR_VERSION,
        "generated_at": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "id": str(digest_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_digest_cursor(value: str) -> DigestCursor:
    """Decode and strictly validate a versioned digest-list cursor."""
    try:
        if not value or not value.isascii():
            raise ValueError
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
            raise ValueError
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != _CURSOR_FIELDS:
            raise ValueError
        if type(payload["v"]) is not int or payload["v"] != _CURSOR_VERSION:
            raise ValueError
        if not isinstance(payload["generated_at"], str) or not isinstance(payload["id"], str):
            raise ValueError
        generated_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            raise ValueError
        digest_id = UUID(payload["id"])
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as exc:
        raise InvalidDigestCursorError("invalid digest cursor") from exc

    return DigestCursor(generated_at=generated_at.astimezone(UTC), digest_id=digest_id)


def _with_entries(statement: Select[tuple[Digest]]) -> Select[tuple[Digest]]:
    """Eagerly load ranked entries, papers, and ordered paper authors."""
    return statement.options(
        selectinload(Digest.entries)
        .selectinload(DigestEntry.paper)
        .selectinload(Paper.author_links)
        .selectinload(PaperAuthor.author)
    )


class DigestRepository:
    """Build and fetch research briefings through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_digests(
        self,
        *,
        user_id: UUID,
        limit: int,
        cursor: DigestCursor | None = None,
    ) -> DigestPageResult:
        """Return one user's digests in stable descending generation order."""
        statement = _with_entries(
            select(Digest)
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc(), Digest.id.desc())
            .limit(limit + 1)
        )
        if cursor is not None:
            statement = statement.where(
                or_(
                    Digest.generated_at < cursor.generated_at,
                    and_(
                        Digest.generated_at == cursor.generated_at,
                        Digest.id < cursor.digest_id,
                    ),
                )
            )

        rows = list((await self._session.scalars(statement)).all())
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_digest_cursor(last.generated_at, last.id)
        return DigestPageResult(items=items, next_cursor=next_cursor)

    async def get_preferences(self, user_id: UUID) -> UserPreference | None:
        """Return the stored preference row for scoring."""
        return await self._session.get(UserPreference, user_id)

    async def list_recent_candidates(
        self, *, since: datetime, limit: int, before: datetime | None = None
    ) -> list[Paper]:
        """Return recent latest-revision papers with a usable summary."""
        latest_version_id = (
            select(PaperVersion.id)
            .where(PaperVersion.paper_id == Paper.id)
            .order_by(PaperVersion.version_number.desc())
            .limit(1)
            .correlate(Paper)
            .scalar_subquery()
        )
        statement = (
            select(Paper)
            .where(
                Paper.published_at >= since,
                Paper.processing_status.in_((ProcessingStatus.READY, ProcessingStatus.PARTIAL)),
                exists(
                    select(PaperSummary.id).where(
                        PaperSummary.paper_id == Paper.id,
                        PaperSummary.paper_version_id == latest_version_id,
                    )
                ),
            )
            .order_by(Paper.published_at.desc(), Paper.id.desc())
            .limit(limit)
            .options(selectinload(Paper.author_links).selectinload(PaperAuthor.author))
        )
        if before is not None:
            statement = statement.where(Paper.published_at < before)
        return list((await self._session.scalars(statement)).all())

    async def mean_chunk_embeddings(self, paper_ids: list[UUID]) -> dict[UUID, tuple[float, ...]]:
        """Return each paper's mean chunk embedding, where one exists."""
        if not paper_ids:
            return {}
        latest_versions = (
            select(
                PaperVersion.paper_id,
                func.max(PaperVersion.version_number).label("version_number"),
            )
            .where(PaperVersion.paper_id.in_(paper_ids))
            .group_by(PaperVersion.paper_id)
            .subquery()
        )
        statement = (
            select(PaperChunk.paper_id, func.avg(PaperChunk.embedding).label("embedding"))
            .join(
                PaperVersion,
                PaperVersion.id == PaperChunk.paper_version_id,
            )
            .join(
                latest_versions,
                and_(
                    latest_versions.c.paper_id == PaperVersion.paper_id,
                    latest_versions.c.version_number == PaperVersion.version_number,
                ),
            )
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
