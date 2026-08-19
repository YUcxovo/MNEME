"""Transactional persistence for Semantic Scholar citation observations."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.graph import Citation
from mneme.models.paper import Paper
from mneme.services.semantic_scholar.types import CitationDirection, SemanticPaper

GRAPH_PREPARED_AS_SOURCE = "graph_prepared_as_source"
GRAPH_PREPARED_AS_TARGET = "graph_prepared_as_target"


class CitationIdentityConflict(RuntimeError):
    """A provider identity points at two different local papers."""


@dataclass(frozen=True, slots=True)
class CitationPersistenceResult:
    """Counts from one idempotent center-paper synchronization."""

    observed: int
    inserted: int
    duplicates: int
    resolved: int
    skipped_self: int


@dataclass(frozen=True, slots=True)
class LocalCitationPersistenceResult:
    """Counts from persisting arXiv-identified edges with two local endpoints."""

    observed: int
    inserted: int
    duplicates: int
    unresolved: int
    skipped_self: int


def _citation_insert(rows: list[dict[str, object]]):
    return postgresql_insert(Citation).values(rows).on_conflict_do_nothing().returning(Citation.id)


class CitationGraphRepository:
    """Persist provider observations without owning commit or rollback."""

    async def persist_local_arxiv_edges(
        self,
        session: AsyncSession,
        *,
        center_paper_id: UUID,
        reference_arxiv_ids: tuple[str, ...],
        citation_arxiv_ids: tuple[str, ...],
        evidence_source: str,
    ) -> LocalCitationPersistenceResult | None:
        """Idempotently persist real directed edges resolved only by local arXiv IDs."""
        requested_ids = set(reference_arxiv_ids) | set(citation_arxiv_ids)
        locked_papers = list(
            (
                await session.scalars(
                    select(Paper)
                    .where(
                        or_(
                            Paper.id == center_paper_id,
                            Paper.arxiv_id.in_(tuple(sorted(requested_ids))),
                        )
                    )
                    .order_by(Paper.id)
                    .with_for_update()
                )
            ).all()
        )
        center = next((paper for paper in locked_papers if paper.id == center_paper_id), None)
        if center is None:
            return None

        by_arxiv = {paper.arxiv_id: paper for paper in locked_papers}
        now = utc_now()
        rows: dict[tuple[UUID, UUID], dict[str, object]] = {}
        preparation_markers: dict[tuple[UUID, UUID], dict[str, bool]] = {}
        skipped_self = 0
        unresolved = 0

        for arxiv_id, references_center in (
            *((arxiv_id, True) for arxiv_id in reference_arxiv_ids),
            *((arxiv_id, False) for arxiv_id in citation_arxiv_ids),
        ):
            neighbor = by_arxiv.get(arxiv_id)
            if neighbor is None:
                unresolved += 1
                continue
            if neighbor.id == center.id:
                skipped_self += 1
                continue
            source_id, target_id = (
                (center.id, neighbor.id) if references_center else (neighbor.id, center.id)
            )
            marker = {
                (
                    GRAPH_PREPARED_AS_SOURCE if source_id == center.id else GRAPH_PREPARED_AS_TARGET
                ): True
            }
            preparation_markers[(source_id, target_id)] = marker
            rows.setdefault(
                (source_id, target_id),
                {
                    "id": uuid4(),
                    "source_paper_id": source_id,
                    "external_source_id": None,
                    "target_paper_id": target_id,
                    "external_target_id": None,
                    "algorithm_weight": None,
                    "algorithm_metadata": {
                        "evidence_source": evidence_source,
                        **marker,
                    },
                    "created_at": now,
                    "updated_at": now,
                },
            )

        inserted = 0
        if rows:
            ordered_edge_ids = sorted(rows)
            result = await session.execute(
                _citation_insert([rows[edge_id] for edge_id in ordered_edge_ids])
            )
            inserted = len(result.scalars().all())
            for source_id, target_id in ordered_edge_ids:
                marker = preparation_markers[(source_id, target_id)]
                await session.execute(
                    update(Citation)
                    .where(
                        Citation.source_paper_id == source_id,
                        Citation.target_paper_id == target_id,
                    )
                    .values(
                        algorithm_metadata=Citation.algorithm_metadata.op("||")(marker),
                        updated_at=now,
                    )
                )
        observed = len(reference_arxiv_ids) + len(citation_arxiv_ids)
        return LocalCitationPersistenceResult(
            observed=observed,
            inserted=inserted,
            duplicates=max(0, observed - unresolved - skipped_self - inserted),
            unresolved=unresolved,
            skipped_self=skipped_self,
        )

    async def persist_neighbors(
        self,
        session: AsyncSession,
        *,
        center_paper_id: UUID,
        center_semantic_scholar_id: str,
        direction: CitationDirection,
        neighbors: tuple[SemanticPaper, ...],
    ) -> CitationPersistenceResult | None:
        """Resolve local identities and upsert one bounded neighbor collection."""
        center = await session.scalar(
            select(Paper).where(Paper.id == center_paper_id).with_for_update()
        )
        if center is None:
            return None
        self._assign_identity(center, center_semantic_scholar_id)

        semantic_ids = {neighbor.paper_id for neighbor in neighbors}
        arxiv_ids = {neighbor.arxiv_id for neighbor in neighbors if neighbor.arxiv_id is not None}
        conditions = [Paper.semantic_scholar_id.in_(semantic_ids)]
        if arxiv_ids:
            conditions.append(Paper.arxiv_id.in_(arxiv_ids))
        local_papers = list(
            (await session.scalars(select(Paper).where(or_(*conditions)).with_for_update())).all()
        )
        by_semantic = {
            paper.semantic_scholar_id: paper
            for paper in local_papers
            if paper.semantic_scholar_id is not None
        }
        by_arxiv = {paper.arxiv_id: paper for paper in local_papers}

        resolved_neighbors: dict[str, Paper] = {}
        for neighbor in neighbors:
            semantic_match = by_semantic.get(neighbor.paper_id)
            arxiv_match = by_arxiv.get(neighbor.arxiv_id) if neighbor.arxiv_id else None
            if (
                semantic_match is not None
                and arxiv_match is not None
                and semantic_match.id != arxiv_match.id
            ):
                raise CitationIdentityConflict(
                    "Semantic Scholar and arXiv identities resolve to different papers"
                )
            local = semantic_match or arxiv_match
            if local is not None:
                self._assign_identity(local, neighbor.paper_id)
                resolved_neighbors[neighbor.paper_id] = local

        await session.flush()
        resolved = 0
        papers_to_resolve = {paper.id: paper for paper in local_papers}
        papers_to_resolve[center.id] = center
        for paper in papers_to_resolve.values():
            if paper.semantic_scholar_id is not None:
                resolved += await self._resolve_existing_edges(session, paper)

        now = utc_now()
        unique_rows: dict[
            tuple[UUID | None, str | None, UUID | None, str | None], dict[str, object]
        ] = {}
        skipped_self = 0
        for neighbor in neighbors:
            local = resolved_neighbors.get(neighbor.paper_id)
            if (
                neighbor.paper_id == center_semantic_scholar_id
                or neighbor.arxiv_id == center.arxiv_id
                or (local is not None and local.id == center.id)
            ):
                skipped_self += 1
                continue

            if direction is CitationDirection.REFERENCES:
                source_id, external_source = center.id, None
                target_id = local.id if local is not None else None
                external_target = None if local is not None else neighbor.paper_id
            else:
                source_id = local.id if local is not None else None
                external_source = None if local is not None else neighbor.paper_id
                target_id, external_target = center.id, None
            key = (source_id, external_source, target_id, external_target)
            unique_rows.setdefault(
                key,
                {
                    "id": uuid4(),
                    "source_paper_id": source_id,
                    "external_source_id": external_source,
                    "target_paper_id": target_id,
                    "external_target_id": external_target,
                    "algorithm_weight": None,
                    "algorithm_metadata": {},
                    "created_at": now,
                    "updated_at": now,
                },
            )

        inserted = 0
        if unique_rows:
            result = await session.execute(_citation_insert(list(unique_rows.values())))
            inserted = len(result.scalars().all())
        duplicates = len(neighbors) - skipped_self - inserted
        return CitationPersistenceResult(
            observed=len(neighbors),
            inserted=inserted,
            duplicates=duplicates,
            resolved=resolved,
            skipped_self=skipped_self,
        )

    @staticmethod
    def _assign_identity(paper: Paper, semantic_scholar_id: str) -> None:
        if paper.semantic_scholar_id not in (None, semantic_scholar_id):
            raise CitationIdentityConflict(
                "A local paper already has a different Semantic Scholar identity"
            )
        paper.semantic_scholar_id = semantic_scholar_id

    async def _resolve_existing_edges(self, session: AsyncSession, paper: Paper) -> int:
        semantic_id = paper.semantic_scholar_id
        if semantic_id is None:
            return 0
        resolved = 0
        external_targets = list(
            (
                await session.scalars(
                    select(Citation)
                    .where(Citation.external_target_id == semantic_id)
                    .with_for_update()
                )
            ).all()
        )
        for edge in external_targets:
            if edge.source_paper_id == paper.id:
                await session.delete(edge)
            else:
                existing = await session.scalar(
                    select(Citation).where(
                        Citation.source_paper_id == edge.source_paper_id,
                        Citation.target_paper_id == paper.id,
                    )
                )
                if existing is None:
                    edge.target_paper_id = paper.id
                    edge.external_target_id = None
                else:
                    self._merge_algorithm_metadata(existing, edge)
                    await session.delete(edge)
            resolved += 1

        external_sources = list(
            (
                await session.scalars(
                    select(Citation)
                    .where(Citation.external_source_id == semantic_id)
                    .with_for_update()
                )
            ).all()
        )
        for edge in external_sources:
            if edge.target_paper_id == paper.id:
                await session.delete(edge)
            else:
                existing = await session.scalar(
                    select(Citation).where(
                        Citation.source_paper_id == paper.id,
                        Citation.target_paper_id == edge.target_paper_id,
                    )
                )
                if existing is None:
                    edge.source_paper_id = paper.id
                    edge.external_source_id = None
                else:
                    self._merge_algorithm_metadata(existing, edge)
                    await session.delete(edge)
            resolved += 1
        await session.flush()
        return resolved

    @staticmethod
    def _merge_algorithm_metadata(existing: Citation, unresolved: Citation) -> None:
        if existing.algorithm_weight is None:
            existing.algorithm_weight = unresolved.algorithm_weight
        existing.algorithm_metadata = {
            **unresolved.algorithm_metadata,
            **existing.algorithm_metadata,
        }
