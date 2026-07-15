"""Unit tests for paper keyset cursors and catalog queries."""

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.paper import Paper, ProcessingStatus
from mneme.repositories.paper_catalog import (
    InvalidPaperCursorError,
    PaperCatalogRepository,
    decode_paper_cursor,
    encode_paper_cursor,
)


def _paper(*, published_at: datetime, paper_id: UUID | None = None) -> Paper:
    return Paper(
        id=paper_id or uuid4(),
        arxiv_id="2607.00001",
        title="A paper",
        abstract="An abstract",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        processing_status=ProcessingStatus.METADATA_ONLY,
        published_at=published_at,
        source_updated_at=published_at,
    )


@pytest.mark.base
@pytest.mark.api
def test_paper_cursor_round_trip_normalizes_utc() -> None:
    paper_id = uuid4()
    timestamp = datetime(2026, 7, 15, 9, 30, tzinfo=UTC) + timedelta(hours=8)

    encoded = encode_paper_cursor(timestamp, paper_id)
    decoded = decode_paper_cursor(encoded)

    assert decoded.paper_id == paper_id
    assert decoded.published_at == timestamp.astimezone(UTC)
    assert "=" not in encoded


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not-base64!",
        "e30",
        "eyJ2IjoyLCJwdWJsaXNoZWRfYXQiOiIyMDI2LTA3LTE1VDAwOjAwOjAwWiIsImlkIjoiYmFkIn0",
        "5Lit5paH",
    ],
)
def test_invalid_paper_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidPaperCursorError, match="invalid paper cursor"):
        decode_paper_cursor(cursor)


@pytest.mark.base
@pytest.mark.api
def test_boolean_cursor_version_is_not_treated_as_integer_one() -> None:
    raw = json.dumps(
        {
            "v": True,
            "published_at": "2026-07-15T00:00:00Z",
            "id": str(uuid4()),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    with pytest.raises(InvalidPaperCursorError, match="invalid paper cursor"):
        decode_paper_cursor(cursor)


@pytest.mark.base
@pytest.mark.api
def test_catalog_query_fetches_lookahead_and_builds_next_cursor() -> None:
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)
    papers = [
        _paper(published_at=timestamp, paper_id=UUID(int=3)),
        _paper(published_at=timestamp, paper_id=UUID(int=2)),
        _paper(published_at=timestamp, paper_id=UUID(int=1)),
    ]
    scalar_result = Mock()
    scalar_result.all.return_value = papers
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=scalar_result)
    repository = PaperCatalogRepository(cast(AsyncSession, session))

    page = asyncio.run(repository.list_papers(limit=2))

    assert page.items == papers[:2]
    assert page.next_cursor is not None
    assert decode_paper_cursor(page.next_cursor).paper_id == papers[1].id
    await_args = session.scalars.await_args
    assert await_args is not None
    statement = await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ORDER BY papers.published_at DESC, papers.id DESC" in sql
    assert "LIMIT 3" in sql


@pytest.mark.base
@pytest.mark.api
def test_catalog_query_applies_cursor_and_internal_category_filter() -> None:
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)
    scalar_result = Mock()
    scalar_result.all.return_value = []
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=scalar_result)
    repository = PaperCatalogRepository(cast(AsyncSession, session))

    page = asyncio.run(
        repository.list_papers(
            limit=20,
            cursor=decode_paper_cursor(encode_paper_cursor(timestamp, UUID(int=10))),
            category="cs.AI",
        )
    )

    assert page.items == []
    assert page.next_cursor is None
    await_args = session.scalars.await_args
    assert await_args is not None
    statement = await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "papers.published_at <" in sql
    assert "papers.id <" in sql
    assert "papers.primary_category =" in sql
