"""Tests for arXiv page transaction orchestration and its CLI surface."""

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.cli.fetch_arxiv import build_parser
from mneme.repositories.arxiv_ingestion import (
    ArxivIngestionRepository,
    ArxivPersistenceResult,
)
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.ingestion import ArxivIngestionService
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivFeed, ArxivPaperRecord


def record(arxiv_id: str) -> ArxivPaperRecord:
    """Build a small parsed record for orchestration tests."""
    timestamp = datetime(2026, 7, 1, tzinfo=UTC)
    return ArxivPaperRecord(
        arxiv_id=arxiv_id,
        version_number=1,
        title=arxiv_id,
        abstract="abstract",
        authors=(ArxivAuthorRecord("Author"),),
        categories=("cs.AI",),
        primary_category="cs.AI",
        published_at=timestamp,
        updated_at=timestamp,
        abstract_url=f"https://arxiv.org/abs/{arxiv_id}v1",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}v1",
        source_license=None,
        doi=None,
        comment=None,
        journal_reference=None,
    )


class FakeTransaction:
    """Record transaction boundaries without connecting to a database."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> None:
        self.events.append("begin")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.events.append("commit" if exc_type is None else "rollback")


class FakeSession:
    """Expose the transaction method used by the ingestion service."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.events)


class FakeClient:
    """Return one parsed feed and record when network work occurred."""

    def __init__(self, events: list[str], feed: ArxivFeed) -> None:
        self.events = events
        self.feed = feed

    async def fetch_by_category(self, category: str, *, start: int, max_results: int) -> ArxivFeed:
        self.events.append(f"fetch:{category}:{start}:{max_results}")
        return self.feed


class FakeRepository:
    """Return deterministic persistence outcomes without issuing SQL."""

    def __init__(self, events: list[str], *, fail_on: str | None = None) -> None:
        self.events = events
        self.fail_on = fail_on

    async def upsert_record(
        self, session: AsyncSession, paper: ArxivPaperRecord
    ) -> ArxivPersistenceResult:
        del session
        self.events.append(f"persist:{paper.arxiv_id}")
        if paper.arxiv_id == self.fail_on:
            raise RuntimeError("database failure")
        return ArxivPersistenceResult(
            paper_id=uuid4(),
            version_created=True,
            authors_replaced=paper.arxiv_id.endswith("1"),
        )


def service(
    events: list[str], feed: ArxivFeed, *, fail_on: str | None = None
) -> ArxivIngestionService:
    """Construct the service with typed in-memory collaborators."""
    return ArxivIngestionService(
        cast(ArxivClient, FakeClient(events, feed)),
        cast(AsyncSession, FakeSession(events)),
        repository=cast(
            ArxivIngestionRepository,
            FakeRepository(events, fail_on=fail_on),
        ),
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_fetch_finishes_before_one_feed_transaction_begins() -> None:
    events: list[str] = []
    feed = ArxivFeed(
        records=(record("2607.00001"), record("2607.00002")),
        total_results=2,
        start_index=0,
        items_per_page=2,
    )

    summary = asyncio.run(service(events, feed).ingest_category("cs.AI", max_results=2))

    assert events == [
        "fetch:cs.AI:0:2",
        "begin",
        "persist:2607.00001",
        "persist:2607.00002",
        "commit",
    ]
    assert summary.records_received == 2
    assert summary.versions_created == 2
    assert summary.author_snapshots_replaced == 1


@pytest.mark.base
@pytest.mark.pipeline
def test_record_failure_rolls_back_the_complete_feed() -> None:
    events: list[str] = []
    feed = ArxivFeed(
        records=(record("2607.00001"), record("2607.00002")),
        total_results=2,
        start_index=0,
        items_per_page=2,
    )

    with pytest.raises(RuntimeError, match="database failure"):
        asyncio.run(service(events, feed, fail_on="2607.00002").persist_feed(feed))

    assert events == [
        "begin",
        "persist:2607.00001",
        "persist:2607.00002",
        "rollback",
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_cli_parser_exposes_bounded_page_arguments() -> None:
    arguments = build_parser().parse_args(["cs.LG", "--start", "40", "--max-results", "10"])

    assert arguments.category == "cs.LG"
    assert arguments.start == 40
    assert arguments.max_results == 10
