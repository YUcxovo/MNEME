"""Idempotent orchestration for one paper's Semantic Scholar graph."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mneme.models.paper import Paper
from mneme.repositories.citation_graph import (
    CitationGraphRepository,
    CitationPersistenceResult,
)
from mneme.services.semantic_scholar.client import SemanticScholarClient
from mneme.services.semantic_scholar.types import CitationDirection, SemanticPaper


class SemanticGraphTargetNotFound(RuntimeError):
    """The requested local or provider paper identity does not exist."""


@dataclass(frozen=True, slots=True)
class SemanticGraphSyncSummary:
    """Machine-readable outcome of one two-direction graph synchronization."""

    paper_id: UUID
    arxiv_id: str
    semantic_scholar_id: str
    references: CitationPersistenceResult
    citations: CitationPersistenceResult


class SemanticGraphSyncService:
    """Fetch outside a transaction, then atomically persist both directions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: SemanticScholarClient,
        repository: CitationGraphRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._repository = repository or CitationGraphRepository()

    async def sync(
        self,
        *,
        paper_id: UUID | None = None,
        arxiv_id: str | None = None,
        limit: int,
    ) -> SemanticGraphSyncSummary:
        """Synchronize citations and references for exactly one local paper."""
        if (paper_id is None) == (arxiv_id is None):
            raise ValueError("Provide exactly one of paper_id or arxiv_id")

        async with self._session_factory() as session:
            statement = select(Paper.id, Paper.arxiv_id)
            if paper_id is not None:
                statement = statement.where(Paper.id == paper_id)
            else:
                statement = statement.where(Paper.arxiv_id == arxiv_id)
            target = (await session.execute(statement)).one_or_none()
        if target is None:
            raise SemanticGraphTargetNotFound("The requested local paper does not exist")
        resolved_paper_id, resolved_arxiv_id = target

        provider_papers = await self._client.fetch_papers([f"ARXIV:{resolved_arxiv_id}"])
        center = self._select_center(provider_papers, resolved_arxiv_id)
        references = await self._client.fetch_neighbors(
            center.paper_id,
            CitationDirection.REFERENCES,
            limit=limit,
        )
        citations = await self._client.fetch_neighbors(
            center.paper_id,
            CitationDirection.CITATIONS,
            limit=limit,
        )

        async with self._session_factory() as session, session.begin():
            reference_result = await self._repository.persist_neighbors(
                session,
                center_paper_id=resolved_paper_id,
                center_semantic_scholar_id=center.paper_id,
                direction=CitationDirection.REFERENCES,
                neighbors=references,
            )
            citation_result = await self._repository.persist_neighbors(
                session,
                center_paper_id=resolved_paper_id,
                center_semantic_scholar_id=center.paper_id,
                direction=CitationDirection.CITATIONS,
                neighbors=citations,
            )
            if reference_result is None or citation_result is None:
                raise SemanticGraphTargetNotFound(
                    "The local paper disappeared during graph synchronization"
                )

        return SemanticGraphSyncSummary(
            paper_id=resolved_paper_id,
            arxiv_id=resolved_arxiv_id,
            semantic_scholar_id=center.paper_id,
            references=reference_result,
            citations=citation_result,
        )

    @staticmethod
    def _select_center(provider_papers: tuple[SemanticPaper, ...], arxiv_id: str) -> SemanticPaper:
        for paper in provider_papers:
            if paper.arxiv_id == arxiv_id:
                return paper
        raise SemanticGraphTargetNotFound(
            "Semantic Scholar has no matching record for the requested arXiv paper"
        )
