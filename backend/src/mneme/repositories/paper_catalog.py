"""Read-only paper catalog queries and opaque keyset cursors."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mneme.models.paper import Paper, PaperAuthor

_CURSOR_VERSION: Final = 1
_CURSOR_FIELDS: Final = frozenset({"v", "published_at", "id"})


class InvalidPaperCursorError(ValueError):
    """Raised when an opaque paper cursor is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class PaperCursor:
    """Decoded descending paper-list keyset."""

    published_at: datetime
    paper_id: UUID


@dataclass(frozen=True, slots=True)
class PaperPageResult:
    """One catalog page plus its optional continuation cursor."""

    items: list[Paper]
    next_cursor: str | None


def encode_paper_cursor(published_at: datetime, paper_id: UUID) -> str:
    """Encode a stable `(published_at, id)` keyset as opaque base64url."""
    if published_at.tzinfo is None:
        raise ValueError("paper cursor timestamps must be timezone-aware")

    payload = {
        "v": _CURSOR_VERSION,
        "published_at": published_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "id": str(paper_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_paper_cursor(value: str) -> PaperCursor:
    """Decode and validate a versioned paper-list cursor."""
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
        if not isinstance(payload["published_at"], str) or not isinstance(payload["id"], str):
            raise ValueError
        published_at = datetime.fromisoformat(payload["published_at"].replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            raise ValueError
        paper_id = UUID(payload["id"])
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as exc:
        raise InvalidPaperCursorError("invalid paper cursor") from exc

    return PaperCursor(published_at=published_at.astimezone(UTC), paper_id=paper_id)


def _with_authors(statement: Select[tuple[Paper]]) -> Select[tuple[Paper]]:
    """Eagerly load ordered author links without an N+1 query."""
    return statement.options(selectinload(Paper.author_links).selectinload(PaperAuthor.author))


class PaperCatalogRepository:
    """Query papers using the frozen v0.1 catalog contract."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_papers(
        self,
        *,
        limit: int,
        cursor: PaperCursor | None = None,
        category: str | None = None,
    ) -> PaperPageResult:
        """Return a descending keyset page, fetching one look-ahead row."""
        statement = _with_authors(
            select(Paper).order_by(Paper.published_at.desc(), Paper.id.desc()).limit(limit + 1)
        )
        if cursor is not None:
            statement = statement.where(
                or_(
                    Paper.published_at < cursor.published_at,
                    and_(
                        Paper.published_at == cursor.published_at,
                        Paper.id < cursor.paper_id,
                    ),
                )
            )
        if category is not None:
            statement = statement.where(Paper.primary_category == category)

        rows = list((await self._session.scalars(statement)).all())
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_paper_cursor(last.published_at, last.id)
        return PaperPageResult(items=items, next_cursor=next_cursor)

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        """Return one catalog paper with ordered authors, if it exists."""
        statement = _with_authors(select(Paper).where(Paper.id == paper_id))
        return await self._session.scalar(statement)
