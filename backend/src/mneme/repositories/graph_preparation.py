"""Database boundaries for on-demand citation-graph preparation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mneme.models.artifact import PaperChunk
from mneme.models.graph import Citation
from mneme.models.paper import Paper, PaperVersion
from mneme.repositories.citation_graph import (
    GRAPH_PREPARED_AS_SOURCE,
    GRAPH_PREPARED_AS_TARGET,
    CitationGraphRepository,
    LocalCitationPersistenceResult,
)
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.ingestion import ArxivIngestionService
from mneme.services.arxiv.types import ArxivFeed

_REFERENCE_HEADING = re.compile(
    r"^(?:(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)]?\s+)?"
    r"(?:references|bibliography|works cited|literature cited)"
    r"(?:\s+and\s+notes)?$",
    re.IGNORECASE,
)


def _is_reference_heading(value: str | None) -> bool:
    if value is None:
        return False
    normalized = " ".join(value.strip().rstrip(":").split())
    return _REFERENCE_HEADING.fullmatch(normalized) is not None


@dataclass(frozen=True, slots=True)
class GraphPreparationTarget:
    """Local paper identity required by external citation providers."""

    paper_id: UUID
    arxiv_id: str
    title: str


class GraphPreparationRepository:
    """Own short session scopes around graph preparation reads and writes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        citation_repository: CitationGraphRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._citation_repository = citation_repository or CitationGraphRepository()

    async def get_target(self, paper_id: UUID) -> GraphPreparationTarget | None:
        """Return the requested local arXiv identity."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Paper.id, Paper.arxiv_id, Paper.title).where(Paper.id == paper_id)
                )
            ).one_or_none()
        if row is None:
            return None
        return GraphPreparationTarget(paper_id=row.id, arxiv_id=row.arxiv_id, title=row.title)

    async def has_prepared_neighborhood(self, paper_id: UUID) -> bool:
        """Whether graph preparation has produced a resolved edge for this center."""
        condition = (
            select(Citation.id)
            .where(
                Citation.source_paper_id.is_not(None),
                Citation.target_paper_id.is_not(None),
                or_(
                    and_(
                        Citation.source_paper_id == paper_id,
                        Citation.algorithm_metadata.contains({GRAPH_PREPARED_AS_SOURCE: True}),
                    ),
                    and_(
                        Citation.target_paper_id == paper_id,
                        Citation.algorithm_metadata.contains({GRAPH_PREPARED_AS_TARGET: True}),
                    ),
                ),
            )
            .limit(1)
        )
        async with self._session_factory() as session:
            return bool(await session.scalar(select(exists(condition))))

    async def list_reference_chunks(self, paper_id: UUID) -> tuple[str, ...]:
        """Read reference text from the newest revision with bibliography chunks."""
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        PaperVersion.id,
                        PaperChunk.section_title,
                        PaperChunk.content,
                    )
                    .join(PaperChunk, PaperChunk.paper_version_id == PaperVersion.id)
                    .where(PaperVersion.paper_id == paper_id)
                    .order_by(
                        PaperVersion.version_number.desc(),
                        PaperChunk.chunk_index,
                    )
                )
            ).all()
        selected_version: UUID | None = None
        contents: list[str] = []
        for version_id, section_title, content in rows:
            if not _is_reference_heading(section_title):
                continue
            if selected_version is None:
                selected_version = version_id
            if version_id != selected_version:
                break
            contents.append(content)
        return tuple(contents)

    async def persist_candidates(
        self,
        *,
        arxiv_client: ArxivClient,
        feed: ArxivFeed,
        center_paper_id: UUID,
        reference_arxiv_ids: tuple[str, ...],
        citation_arxiv_ids: tuple[str, ...],
        evidence_source: str,
    ) -> LocalCitationPersistenceResult | None:
        """Ingest verified arXiv metadata, then persist its actual directed edges."""
        async with self._session_factory() as session:
            await ArxivIngestionService(arxiv_client, session).persist_feed_detailed(feed)
        async with self._session_factory() as session, session.begin():
            return await self._citation_repository.persist_local_arxiv_edges(
                session,
                center_paper_id=center_paper_id,
                reference_arxiv_ids=reference_arxiv_ids,
                citation_arxiv_ids=citation_arxiv_ids,
                evidence_source=evidence_source,
            )
