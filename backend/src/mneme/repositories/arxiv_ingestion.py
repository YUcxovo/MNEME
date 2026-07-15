"""Transactional persistence primitives for normalized arXiv metadata."""

from dataclasses import dataclass
from datetime import datetime
from unicodedata import normalize
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.paper import Author, Paper, PaperAuthor, PaperVersion, ProcessingStatus
from mneme.services.arxiv.types import ArxivPaperRecord


@dataclass(frozen=True, slots=True)
class ArxivPersistenceResult:
    """Outcome of persisting one observed arXiv record."""

    paper_id: UUID
    version_created: bool
    authors_replaced: bool


def normalize_author_name(name: str) -> tuple[str, str]:
    """Return stable display and identity forms for one author name."""
    display_name = " ".join(normalize("NFKC", name).split())
    normalized_name = display_name.casefold()
    if not normalized_name:
        raise ValueError("Author name must not be empty")
    if len(display_name) > 200 or len(normalized_name) > 200:
        raise ValueError("Author name exceeds the database limit")
    return display_name, normalized_name


def _paper_upsert(record: ArxivPaperRecord, *, paper_id: UUID, now: datetime):
    """Build a newer-only snapshot upsert keyed by the base arXiv identifier."""
    statement = postgresql_insert(Paper).values(
        id=paper_id,
        arxiv_id=record.arxiv_id,
        title=record.title,
        abstract=record.abstract,
        primary_category=record.primary_category,
        categories=list(record.categories),
        pdf_url=record.pdf_url,
        source_license=record.source_license,
        processing_status=ProcessingStatus.METADATA_ONLY,
        published_at=record.published_at,
        source_updated_at=record.updated_at,
        created_at=now,
        updated_at=now,
    )
    excluded = statement.excluded
    return statement.on_conflict_do_update(
        constraint="uq_papers_arxiv_id",
        set_={
            "title": excluded.title,
            "abstract": excluded.abstract,
            "primary_category": excluded.primary_category,
            "categories": excluded.categories,
            "pdf_url": excluded.pdf_url,
            "source_license": excluded.source_license,
            "processing_status": ProcessingStatus.METADATA_ONLY,
            "published_at": excluded.published_at,
            "source_updated_at": excluded.source_updated_at,
            "updated_at": now,
        },
        where=excluded.source_updated_at > Paper.source_updated_at,
    ).returning(Paper.id)


def _version_insert(record: ArxivPaperRecord, *, paper_id: UUID, now: datetime):
    """Build an idempotent insert for one observed arXiv revision."""
    return (
        postgresql_insert(PaperVersion)
        .values(
            id=uuid4(),
            paper_id=paper_id,
            version_number=record.version_number,
            submitted_at=record.updated_at,
            source_checksum=None,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_paper_versions_paper_version")
        .returning(PaperVersion.id)
    )


def _author_upsert(display_name: str, normalized_name: str, *, now: datetime):
    """Build a race-safe author identity upsert."""
    statement = postgresql_insert(Author).values(
        id=uuid4(),
        display_name=display_name,
        normalized_name=normalized_name,
        semantic_scholar_id=None,
        created_at=now,
    )
    return statement.on_conflict_do_update(
        constraint="uq_authors_normalized_name",
        set_={"display_name": statement.excluded.display_name},
    ).returning(Author.id)


class ArxivIngestionRepository:
    """Persist arXiv records without owning commit or rollback boundaries."""

    async def upsert_record(
        self, session: AsyncSession, record: ArxivPaperRecord
    ) -> ArxivPersistenceResult:
        """Persist a revision and conditionally refresh its latest snapshot."""
        now = utc_now()
        paper_result = await session.execute(_paper_upsert(record, paper_id=uuid4(), now=now))
        paper_id = paper_result.scalar_one_or_none()

        snapshot_is_current = paper_id is not None
        if paper_id is None:
            existing_result = await session.execute(
                select(Paper.id, Paper.source_updated_at).where(Paper.arxiv_id == record.arxiv_id)
            )
            paper_id, stored_updated_at = existing_result.one()
            snapshot_is_current = record.updated_at >= stored_updated_at

        version_result = await session.execute(_version_insert(record, paper_id=paper_id, now=now))
        version_created = version_result.scalar_one_or_none() is not None

        if snapshot_is_current:
            await self._replace_authors(session, paper_id, record, now=now)

        return ArxivPersistenceResult(
            paper_id=paper_id,
            version_created=version_created,
            authors_replaced=snapshot_is_current,
        )

    async def _replace_authors(
        self,
        session: AsyncSession,
        paper_id: UUID,
        record: ArxivPaperRecord,
        *,
        now: datetime,
    ) -> None:
        normalized_authors: list[tuple[str, str]] = []
        seen: set[str] = set()
        for author in record.authors:
            display_name, normalized_name = normalize_author_name(author.name)
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            normalized_authors.append((display_name, normalized_name))

        author_ids: list[UUID] = []
        for display_name, normalized_name in normalized_authors:
            result = await session.execute(_author_upsert(display_name, normalized_name, now=now))
            author_ids.append(result.scalar_one())

        await session.execute(delete(PaperAuthor).where(PaperAuthor.paper_id == paper_id))
        if author_ids:
            await session.execute(
                insert(PaperAuthor),
                [
                    {
                        "paper_id": paper_id,
                        "author_id": author_id,
                        "author_order": order,
                    }
                    for order, author_id in enumerate(author_ids)
                ],
            )
