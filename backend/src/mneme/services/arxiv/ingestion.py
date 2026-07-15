"""One-page transaction orchestration for arXiv metadata ingestion."""

from dataclasses import dataclass

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
        feed = await self._client.fetch_by_category(
            category,
            start=start,
            max_results=max_results,
        )
        return await self.persist_feed(feed)

    async def persist_feed(self, feed: ArxivFeed) -> ArxivIngestionSummary:
        """Persist an already parsed feed in one all-or-nothing transaction."""
        versions_created = 0
        author_snapshots_replaced = 0
        async with self._session.begin():
            for record in feed.records:
                result = await self._repository.upsert_record(self._session, record)
                versions_created += result.version_created
                author_snapshots_replaced += result.authors_replaced

        return ArxivIngestionSummary(
            records_received=len(feed.records),
            versions_created=versions_created,
            author_snapshots_replaced=author_snapshots_replaced,
        )
