"""On-demand preparation of real, locally renderable citation neighborhoods."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import structlog

from mneme.repositories.graph_preparation import (
    GraphPreparationRepository,
    GraphPreparationTarget,
)
from mneme.services.arxiv.client import ArxivClient, ArxivClientError
from mneme.services.arxiv.parser import ArxivParseError
from mneme.services.arxiv.types import ArxivFeed, ArxivPaperRecord
from mneme.services.openalex import OpenAlexClient, OpenAlexClientError
from mneme.services.seed_graph import (
    InsufficientSeedGraphCandidates,
    SeedGraphCandidateService,
    SeedGraphMetadataUnavailable,
)
from mneme.services.semantic_scholar import SemanticPaper, SemanticScholarClientError

logger = structlog.get_logger(__name__)

GraphEvidenceSource = Literal[
    "cache",
    "semantic_scholar",
    "openalex",
    "parsed_references",
    "none",
]
_EXPLICIT_ARXIV_REFERENCE = re.compile(
    r"(?:"
    r"\barxiv\s*:\s*"
    r"|https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/"
    r")"
    r"(?P<base>(?:\d{4}\.\d{4,5}|[A-Za-z0-9._-]+/\d{7}))"
    r"(?:v[1-9]\d*)?(?:\.pdf)?"
    r"(?![A-Za-z0-9_/-]|\.[A-Za-z0-9_-])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GraphPreparationResult:
    """Safe orchestration outcome used for logging and route control flow."""

    paper_id: UUID
    evidence_source: GraphEvidenceSource
    cached: bool
    resolved_neighbors: int


@dataclass(frozen=True, slots=True)
class _CandidateEdges:
    references: tuple[str, ...]
    citations: tuple[str, ...]

    @property
    def all_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.references, *self.citations)))


class GraphPreparationService:
    """Prepare a graph from external evidence without inventing relationships."""

    def __init__(
        self,
        repository: GraphPreparationRepository,
        arxiv_client: ArxivClient,
        seed_graph_service: SeedGraphCandidateService,
        openalex_client: OpenAlexClient,
    ) -> None:
        self._repository = repository
        self._arxiv_client = arxiv_client
        self._seed_graph_service = seed_graph_service
        self._openalex_client = openalex_client

    async def prepare(
        self,
        paper_id: UUID,
        *,
        neighbor_limit: int,
    ) -> GraphPreparationResult | None:
        """Prepare one bounded graph and return without failure when evidence is absent."""
        if not 1 <= neighbor_limit <= 100:
            raise ValueError("Graph preparation limit must be between 1 and 100")
        target = await self._repository.get_target(paper_id)
        if target is None:
            return None
        if await self._repository.has_prepared_neighborhood(paper_id):
            return GraphPreparationResult(
                paper_id=paper_id,
                evidence_source="cache",
                cached=True,
                resolved_neighbors=0,
            )

        semantic_edges = await self._semantic_scholar_edges(target, neighbor_limit)
        if semantic_edges is not None:
            outcome = await self._persist_edges(
                target,
                semantic_edges,
                evidence_source="semantic_scholar",
            )
            if outcome is not None:
                return outcome

        openalex_edges = await self._openalex_edges(target, neighbor_limit)
        if openalex_edges is not None:
            outcome = await self._persist_edges(
                target,
                openalex_edges,
                evidence_source="openalex",
            )
            if outcome is not None:
                return outcome

        parsed_edges = await self._parsed_reference_edges(target, neighbor_limit)
        if parsed_edges.references:
            outcome = await self._persist_edges(
                target,
                parsed_edges,
                evidence_source="parsed_references",
            )
            if outcome is not None:
                return outcome

        logger.info("graph_preparation_no_resolvable_neighbors", paper_id=str(paper_id))
        return GraphPreparationResult(
            paper_id=paper_id,
            evidence_source="none",
            cached=False,
            resolved_neighbors=0,
        )

    async def _semantic_scholar_edges(
        self,
        target: GraphPreparationTarget,
        limit: int,
    ) -> _CandidateEdges | None:
        try:
            neighborhood = await self._seed_graph_service.discover_neighborhood(
                target.arxiv_id,
                neighbor_limit=limit,
            )
        except (
            InsufficientSeedGraphCandidates,
            SemanticScholarClientError,
            ValueError,
        ) as error:
            logger.info(
                "graph_preparation_semantic_scholar_unavailable",
                paper_id=str(target.paper_id),
                error_type=type(error).__name__,
            )
            return None
        edges = _CandidateEdges(
            references=self._semantic_arxiv_ids(
                neighborhood.references,
                target.arxiv_id,
                limit,
            ),
            citations=self._semantic_arxiv_ids(
                neighborhood.citations,
                target.arxiv_id,
                limit,
            ),
        )
        return edges if edges.all_ids else None

    async def _openalex_edges(
        self,
        target: GraphPreparationTarget,
        limit: int,
    ) -> _CandidateEdges | None:
        try:
            neighborhood = await self._openalex_client.fetch_neighborhood(
                arxiv_id=target.arxiv_id,
                title=target.title,
                limit=limit,
            )
        except OpenAlexClientError as error:
            logger.info(
                "graph_preparation_openalex_unavailable",
                paper_id=str(target.paper_id),
                error_type=type(error).__name__,
            )
            return None
        if neighborhood is None:
            return None
        edges = _CandidateEdges(
            references=neighborhood.references,
            citations=neighborhood.citations,
        )
        return edges if edges.all_ids else None

    async def _parsed_reference_edges(
        self,
        target: GraphPreparationTarget,
        limit: int,
    ) -> _CandidateEdges:
        contents = await self._repository.list_reference_chunks(target.paper_id)
        ordered: list[str] = []
        seen = {target.arxiv_id}
        for content in contents:
            for match in _EXPLICIT_ARXIV_REFERENCE.finditer(content):
                arxiv_id = match.group("base")
                if arxiv_id in seen:
                    continue
                seen.add(arxiv_id)
                ordered.append(arxiv_id)
                if len(ordered) == limit:
                    return _CandidateEdges(references=tuple(ordered), citations=())
        return _CandidateEdges(references=tuple(ordered), citations=())

    async def _persist_edges(
        self,
        target: GraphPreparationTarget,
        edges: _CandidateEdges,
        *,
        evidence_source: Literal["semantic_scholar", "openalex", "parsed_references"],
    ) -> GraphPreparationResult | None:
        try:
            records = await self._seed_graph_service.resolve_available_arxiv_records(
                edges.all_ids,
                limit=len(edges.all_ids),
            )
        except (
            ArxivClientError,
            ArxivParseError,
            SeedGraphMetadataUnavailable,
            ValueError,
        ) as error:
            logger.info(
                "graph_preparation_arxiv_metadata_unavailable",
                paper_id=str(target.paper_id),
                evidence_source=evidence_source,
                error_type=type(error).__name__,
            )
            return None
        records_by_id = {record.arxiv_id: record for record in records}
        if not records_by_id:
            return None
        references = tuple(value for value in edges.references if value in records_by_id)
        citations = tuple(value for value in edges.citations if value in records_by_id)
        if not references and not citations:
            return None
        feed = self._feed(
            tuple(records_by_id[value] for value in edges.all_ids if value in records_by_id)
        )
        persistence = await self._repository.persist_candidates(
            arxiv_client=self._arxiv_client,
            feed=feed,
            center_paper_id=target.paper_id,
            reference_arxiv_ids=references,
            citation_arxiv_ids=citations,
            evidence_source=evidence_source,
        )
        if persistence is None:
            return None
        logger.info(
            "graph_preparation_completed",
            paper_id=str(target.paper_id),
            evidence_source=evidence_source,
            observed=persistence.observed,
            inserted=persistence.inserted,
            duplicates=persistence.duplicates,
        )
        return GraphPreparationResult(
            paper_id=target.paper_id,
            evidence_source=evidence_source,
            cached=False,
            resolved_neighbors=persistence.observed
            - persistence.unresolved
            - persistence.skipped_self,
        )

    @staticmethod
    def _semantic_arxiv_ids(
        papers: tuple[SemanticPaper, ...],
        center_arxiv_id: str,
        limit: int,
    ) -> tuple[str, ...]:
        ordered: list[str] = []
        seen = {center_arxiv_id}
        for paper in papers:
            arxiv_id = paper.arxiv_id
            if arxiv_id is None or arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            ordered.append(arxiv_id)
            if len(ordered) == limit:
                break
        return tuple(ordered)

    @staticmethod
    def _feed(records: tuple[ArxivPaperRecord, ...]) -> ArxivFeed:
        return ArxivFeed(
            records=records,
            total_results=len(records),
            start_index=0,
            items_per_page=len(records),
        )
