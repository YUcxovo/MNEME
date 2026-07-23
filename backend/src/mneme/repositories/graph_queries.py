"""Bounded database reads for paper-centered citation graphs."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.graph.algorithms import GraphEdge, GraphNode
from mneme.graph.contracts import GraphSnapshot
from mneme.models.graph import Citation
from mneme.models.paper import Paper

_EDGE_EXPANSION_FACTOR = 20


class SqlGraphRepository:
    """Traverse locally resolved citation edges in both directions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_ego_graph(
        self, paper_id: UUID, *, depth: int, max_nodes: int
    ) -> GraphSnapshot | None:
        """Return a deterministic induced subgraph bounded before algorithm work."""
        if depth not in (1, 2):
            raise ValueError("Graph depth must be 1 or 2")
        if not 1 <= max_nodes <= 200:
            raise ValueError("Graph max_nodes must be between 1 and 200")

        center = await self._session.get(Paper, paper_id)
        if center is None:
            return None

        selected: dict[UUID, Paper] = {center.id: center}
        frontier = {center.id}
        for _ in range(depth):
            if not frontier or len(selected) >= max_nodes:
                break
            candidate_rows = (
                await self._session.execute(
                    select(Citation.source_paper_id, Citation.target_paper_id)
                    .where(
                        Citation.source_paper_id.is_not(None),
                        Citation.target_paper_id.is_not(None),
                        or_(
                            Citation.source_paper_id.in_(frontier),
                            Citation.target_paper_id.in_(frontier),
                        ),
                    )
                    .order_by(Citation.created_at, Citation.id)
                    .limit(max_nodes * _EDGE_EXPANSION_FACTOR)
                )
            ).all()
            candidates: set[UUID] = set()
            for source_id, target_id in candidate_rows:
                if source_id is not None and source_id not in selected:
                    candidates.add(source_id)
                if target_id is not None and target_id not in selected:
                    candidates.add(target_id)
            if not candidates:
                break

            remaining = max_nodes - len(selected)
            papers = list(
                (
                    await self._session.scalars(
                        select(Paper)
                        .where(Paper.id.in_(candidates))
                        .order_by(Paper.published_at.desc(), Paper.id)
                        .limit(remaining)
                    )
                ).all()
            )
            frontier = {paper.id for paper in papers}
            selected.update((paper.id, paper) for paper in papers)

        selected_ids = set(selected)
        edges: tuple[GraphEdge, ...] = ()
        if len(selected_ids) > 1:
            edge_rows = (
                await self._session.execute(
                    select(
                        Citation.source_paper_id,
                        Citation.target_paper_id,
                        Citation.algorithm_weight,
                    )
                    .where(
                        Citation.source_paper_id.in_(selected_ids),
                        Citation.target_paper_id.in_(selected_ids),
                    )
                    .order_by(Citation.source_paper_id, Citation.target_paper_id)
                    .limit(max_nodes * max_nodes)
                )
            ).all()
            edges = tuple(
                GraphEdge(source=source_id, target=target_id, weight=weight)
                for source_id, target_id, weight in edge_rows
                if source_id is not None and target_id is not None
            )

        nodes = {
            local_id: GraphNode(
                id=local_id,
                title=paper.title,
                category=paper.primary_category,
            )
            for local_id, paper in selected.items()
        }
        return GraphSnapshot(center_id=center.id, nodes=nodes, edges=edges)
