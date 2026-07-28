"""Citation-backed paper selection for seed onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mneme.repositories.citation_graph import (
    CitationGraphRepository,
    CitationPersistenceResult,
)
from mneme.services.arxiv.client import ArxivClient, ArxivClientError
from mneme.services.arxiv.parser import ArxivParseError
from mneme.services.arxiv.types import ArxivFeed, ArxivPaperRecord
from mneme.services.semantic_scholar import (
    CitationDirection,
    SemanticPaper,
    SemanticScholarClient,
)


class InsufficientSeedGraphCandidates(RuntimeError):
    """The provider neighborhood cannot supply the requested local papers."""


class SeedGraphMetadataUnavailable(RuntimeError):
    """arXiv metadata for a discovered citation neighborhood is unavailable."""


@dataclass(frozen=True, slots=True)
class SeedGraphCandidates:
    """A bounded set of arXiv papers connected to one seed paper."""

    feed: ArxivFeed
    center: SemanticPaper
    references: tuple[SemanticPaper, ...]
    citations: tuple[SemanticPaper, ...]


@dataclass(frozen=True, slots=True)
class SeedGraphPersistence:
    """Persistence outcomes for both citation directions."""

    references: CitationPersistenceResult
    citations: CitationPersistenceResult


class SeedGraphCandidateService:
    """Discover arXiv-resolvable neighbors and persist their citation edges."""

    def __init__(
        self,
        arxiv_client: ArxivClient,
        semantic_client: SemanticScholarClient,
        repository: CitationGraphRepository | None = None,
    ) -> None:
        self._arxiv_client = arxiv_client
        self._semantic_client = semantic_client
        self._repository = repository or CitationGraphRepository()

    async def discover(
        self,
        seed_arxiv_id: str,
        *,
        library_size: int,
        neighbor_limit: int,
    ) -> SeedGraphCandidates:
        """Return exactly ``library_size`` real arXiv neighbors in stable order."""
        if library_size < 1:
            raise ValueError("library_size must be positive")
        if neighbor_limit < library_size:
            raise ValueError("neighbor_limit must cover the requested library")

        center, references = await self._semantic_client.fetch_paper_references(
            f"ARXIV:{seed_arxiv_id}",
            limit=neighbor_limit,
        )
        self._validate_center(center, seed_arxiv_id)
        citations: tuple[SemanticPaper, ...] = ()
        if len(self._ordered_arxiv_ids(seed_arxiv_id, references, ())) < library_size:
            citations = await self._semantic_client.fetch_neighbors(
                center.paper_id,
                CitationDirection.CITATIONS,
                limit=neighbor_limit,
            )
        candidate_ids = self._ordered_arxiv_ids(
            seed_arxiv_id,
            references,
            citations,
        )
        if len(candidate_ids) < library_size:
            raise InsufficientSeedGraphCandidates(
                "The seed has too few arXiv-resolvable citation neighbors"
            )

        selected_records = await self._resolve_arxiv_records(
            candidate_ids,
            library_size=library_size,
        )
        if len(selected_records) != library_size:
            raise InsufficientSeedGraphCandidates(
                "arXiv did not return enough citation-neighbor records"
            )

        return SeedGraphCandidates(
            feed=ArxivFeed(
                records=selected_records,
                total_results=len(selected_records),
                start_index=0,
                items_per_page=len(selected_records),
            ),
            center=center,
            references=references,
            citations=citations,
        )

    async def _resolve_arxiv_records(
        self,
        candidate_ids: tuple[str, ...],
        *,
        library_size: int,
    ) -> tuple[ArxivPaperRecord, ...]:
        """Resolve provider-ordered metadata without discarding neighbors after one 429."""
        records_by_id: dict[str, ArxivPaperRecord] = {}
        batch_size = library_size
        for start in range(0, len(candidate_ids), batch_size):
            batch = candidate_ids[start : start + batch_size]
            try:
                feed = await self._arxiv_client.fetch_by_ids(batch)
            except (ArxivClientError, ArxivParseError, ValueError):
                feed = await self._resolve_batch_individually(batch)
            for record in feed.records:
                if record.arxiv_id in batch:
                    records_by_id.setdefault(record.arxiv_id, record)
            selected = tuple(
                records_by_id[arxiv_id] for arxiv_id in candidate_ids if arxiv_id in records_by_id
            )[:library_size]
            if len(selected) == library_size:
                return selected
        return tuple(
            records_by_id[arxiv_id] for arxiv_id in candidate_ids if arxiv_id in records_by_id
        )[:library_size]

    async def _resolve_batch_individually(self, batch: tuple[str, ...]) -> ArxivFeed:
        """Retry a failed batch as single-paper requests on the same rate-limited client."""
        records = []
        for arxiv_id in batch:
            try:
                feed = await self._arxiv_client.fetch_by_ids((arxiv_id,))
            except (ArxivClientError, ArxivParseError, ValueError) as error:
                raise SeedGraphMetadataUnavailable(
                    "arXiv citation-neighbor metadata remained unavailable after retry"
                ) from error
            records.extend(record for record in feed.records if record.arxiv_id == arxiv_id)
        return ArxivFeed(
            records=tuple(records),
            total_results=len(records),
            start_index=0,
            items_per_page=len(records),
        )

    async def persist(
        self,
        session: AsyncSession,
        *,
        center_paper_id: UUID,
        candidates: SeedGraphCandidates,
    ) -> SeedGraphPersistence:
        """Persist both directions after candidate papers enter the local catalog."""
        async with session.begin():
            references = await self._repository.persist_neighbors(
                session,
                center_paper_id=center_paper_id,
                center_semantic_scholar_id=candidates.center.paper_id,
                direction=CitationDirection.REFERENCES,
                neighbors=candidates.references,
            )
            citations = await self._repository.persist_neighbors(
                session,
                center_paper_id=center_paper_id,
                center_semantic_scholar_id=candidates.center.paper_id,
                direction=CitationDirection.CITATIONS,
                neighbors=candidates.citations,
            )
            if references is None or citations is None:
                raise RuntimeError("The seed paper disappeared during graph persistence")
        return SeedGraphPersistence(references=references, citations=citations)

    @staticmethod
    def _validate_center(
        center: SemanticPaper,
        seed_arxiv_id: str,
    ) -> None:
        if center.arxiv_id != seed_arxiv_id:
            raise InsufficientSeedGraphCandidates(
                "Semantic Scholar has no matching record for the seed paper"
            )

    @staticmethod
    def _ordered_arxiv_ids(
        seed_arxiv_id: str,
        references: tuple[SemanticPaper, ...],
        citations: tuple[SemanticPaper, ...],
    ) -> tuple[str, ...]:
        ordered: list[str] = []
        seen = {seed_arxiv_id}
        for paper in (*references, *citations):
            arxiv_id = paper.arxiv_id
            if arxiv_id is None or arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            ordered.append(arxiv_id)
        return tuple(ordered)
