"""One-page transaction orchestration for arXiv metadata ingestion."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mneme.repositories.arxiv_ingestion import ArxivIngestionRepository
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.types import ArxivFeed


@dataclass(frozen=True, slots=True)
class ArxivIngestionSummary:
    """Aggregate result for one fetched Atom page."""

    records_received: int
    versions_created: int
    author_snapshots_replaced: int


@dataclass(frozen=True, slots=True)
class ArxivObservedRevision:
    """Exact database identity for one revision observed in a fetched page."""

    paper_id: UUID
    paper_version_id: UUID
    arxiv_id: str
    version_number: int
    version_created: bool


@dataclass(frozen=True, slots=True)
class ArxivIngestionResult:
    """Counts plus revision identities needed by downstream durable jobs."""

    summary: ArxivIngestionSummary
    revisions: tuple[ArxivObservedRevision, ...]


class ArxivIngestionService:
    """Fetch outside a transaction, then atomically persist the complete page."""

    def __init__(
        self,
        client: ArxivClient,
        session: AsyncSession,
        *,
        repository: ArxivIngestionRepository | None = None,
    ) -> None:
        self._client = client
        self._session = session
        self._repository = repository or ArxivIngestionRepository()

    async def ingest_category(
        self, category: str, *, start: int = 0, max_results: int = 20
    ) -> ArxivIngestionSummary:
        """Fetch, parse, and persist one category page as a single transaction."""
        result = await self.ingest_category_detailed(
            category,
            start=start,
            max_results=max_results,
        )
        return result.summary

    async def ingest_category_detailed(
        self, category: str, *, start: int = 0, max_results: int = 20
    ) -> ArxivIngestionResult:
        """Fetch and persist a page while retaining exact revision identities."""
        feed = await self._client.fetch_by_category(
            category,
            start=start,
            max_results=max_results,
        )
        return await self.persist_feed_detailed(feed)

    async def persist_feed(self, feed: ArxivFeed) -> ArxivIngestionSummary:
        """Persist an already parsed feed in one all-or-nothing transaction."""
        result = await self.persist_feed_detailed(feed)
        return result.summary

    async def persist_feed_detailed(self, feed: ArxivFeed) -> ArxivIngestionResult:
        """Persist a feed and expose every exact revision identity."""
        versions_created = 0
        author_snapshots_replaced = 0
        revisions: list[ArxivObservedRevision] = []
        async with self._session.begin():
            for record in feed.records:
                result = await self._repository.upsert_record(self._session, record)
                versions_created += result.version_created
                author_snapshots_replaced += result.authors_replaced
                revisions.append(
                    ArxivObservedRevision(
                        paper_id=result.paper_id,
                        paper_version_id=result.paper_version_id,
                        arxiv_id=record.arxiv_id,
                        version_number=record.version_number,
                        version_created=result.version_created,
                    )
                )

        return ArxivIngestionResult(
            summary=ArxivIngestionSummary(
                records_received=len(feed.records),
                versions_created=versions_created,
                author_snapshots_replaced=author_snapshots_replaced,
            ),
            revisions=tuple(revisions),
        )
