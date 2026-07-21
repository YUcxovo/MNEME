"""Unit tests for race-safe arXiv metadata persistence."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.repositories.arxiv_ingestion import (
    ArxivIngestionRepository,
    normalize_author_name,
)
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivPaperRecord


def paper_record(
    *,
    updated_at: datetime | None = None,
    authors: tuple[ArxivAuthorRecord, ...] | None = None,
) -> ArxivPaperRecord:
    """Build one normalized record for persistence tests."""
    published_at = datetime(2026, 7, 1, tzinfo=UTC)
    return ArxivPaperRecord(
        arxiv_id="2607.00001",
        version_number=2,
        title="A paper",
        abstract="An abstract",
        authors=authors
        or (
            ArxivAuthorRecord(" Alice   Smith "),
            ArxivAuthorRecord("Bob Jones"),
        ),
        categories=("cs.AI", "cs.LG"),
        primary_category="cs.AI",
        published_at=published_at,
        updated_at=updated_at or published_at + timedelta(days=1),
        abstract_url="https://arxiv.org/abs/2607.00001v2",
        pdf_url="https://arxiv.org/pdf/2607.00001v2",
        source_license="https://creativecommons.org/licenses/by/4.0/",
        doi=None,
        comment=None,
        journal_reference=None,
    )


def scalar_result(value: UUID | None) -> MagicMock:
    """Return a minimal SQLAlchemy result double."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result


@pytest.mark.base
@pytest.mark.pipeline
def test_upsert_uses_database_conflict_constraints_and_ordered_authors() -> None:
    async def exercise() -> tuple[AsyncMock, UUID, UUID, UUID]:
        session = AsyncMock(spec=AsyncSession)
        paper_id = uuid4()
        version_id = uuid4()
        alice_id = uuid4()
        bob_id = uuid4()
        session.execute.side_effect = [
            scalar_result(paper_id),
            scalar_result(version_id),
            scalar_result(alice_id),
            scalar_result(bob_id),
            MagicMock(),
            MagicMock(),
        ]

        outcome = await ArxivIngestionRepository().upsert_record(session, paper_record())

        assert outcome.paper_id == paper_id
        assert outcome.paper_version_id == version_id
        assert outcome.version_created
        assert outcome.authors_replaced
        return session, paper_id, alice_id, bob_id

    session, paper_id, alice_id, bob_id = asyncio.run(exercise())
    calls = session.execute.await_args_list
    paper_sql = str(calls[0].args[0].compile(dialect=postgresql.dialect()))
    version_sql = str(calls[1].args[0].compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT ON CONSTRAINT uq_papers_arxiv_id DO UPDATE" in paper_sql
    assert "WHERE excluded.source_updated_at > papers.source_updated_at" in paper_sql
    assert "ON CONFLICT ON CONSTRAINT uq_paper_versions_paper_version DO NOTHING" in version_sql

    author_sql = str(calls[2].args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_authors_normalized_name DO UPDATE" in author_sql
    assert calls[-1].args[1] == [
        {"paper_id": paper_id, "author_id": alice_id, "author_order": 0},
        {"paper_id": paper_id, "author_id": bob_id, "author_order": 1},
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_older_record_adds_revision_without_regressing_authors() -> None:
    async def exercise() -> tuple[AsyncMock, UUID]:
        session = AsyncMock(spec=AsyncSession)
        paper_id = uuid4()
        rejected_upsert = scalar_result(None)
        existing = MagicMock()
        incoming = paper_record()
        existing.one.return_value = (paper_id, incoming.updated_at + timedelta(days=1))
        session.execute.side_effect = [rejected_upsert, existing, scalar_result(uuid4())]

        outcome = await ArxivIngestionRepository().upsert_record(session, incoming)

        assert outcome.paper_id == paper_id
        assert outcome.version_created
        assert not outcome.authors_replaced
        return session, paper_id

    session, _ = asyncio.run(exercise())
    assert session.execute.await_count == 3


@pytest.mark.base
@pytest.mark.pipeline
def test_equal_snapshot_can_repair_authors_and_deduplicates_identities() -> None:
    async def exercise() -> tuple[AsyncMock, UUID, UUID]:
        session = AsyncMock(spec=AsyncSession)
        paper_id = uuid4()
        author_id = uuid4()
        incoming = paper_record(
            authors=(
                ArxivAuthorRecord("Alice Smith"),
                ArxivAuthorRecord(" alice  smith "),
            )
        )
        rejected_upsert = scalar_result(None)
        existing = MagicMock()
        existing.one.return_value = (paper_id, incoming.updated_at)
        existing_version_id = uuid4()
        session.execute.side_effect = [
            rejected_upsert,
            existing,
            scalar_result(None),
            scalar_result(existing_version_id),
            scalar_result(author_id),
            MagicMock(),
            MagicMock(),
        ]

        outcome = await ArxivIngestionRepository().upsert_record(session, incoming)

        assert outcome.authors_replaced
        assert not outcome.version_created
        assert outcome.paper_version_id == existing_version_id
        return session, paper_id, author_id

    session, paper_id, author_id = asyncio.run(exercise())
    assert session.execute.await_args_list[-1].args[1] == [
        {"paper_id": paper_id, "author_id": author_id, "author_order": 0}
    ]


@pytest.mark.base
@pytest.mark.pipeline
def test_author_normalization_is_unicode_stable_and_rejects_empty_names() -> None:
    assert normalize_author_name("  Alice\tSMITH ") == ("Alice SMITH", "alice smith")
    assert normalize_author_name("\uff21lice") == ("Alice", "alice")
    assert normalize_author_name("Stra\u00dfe")[1] == "strasse"
    with pytest.raises(ValueError, match="empty"):
        normalize_author_name(" \t ")
