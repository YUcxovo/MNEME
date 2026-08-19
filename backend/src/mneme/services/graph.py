"""Public citation-graph assembly with a deterministic safe fallback."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import structlog

from mneme.graph.algorithms import GraphView, build_graph_view
from mneme.graph.contracts import GraphRepository, GraphSnapshot

logger = structlog.get_logger(__name__)

GRAPH_VERSION = "citation-graph-v1"
GraphAlgorithmStatus = Literal["ready", "fallback"]
GraphViewBuilder = Callable[..., GraphView]


@dataclass(frozen=True, slots=True)
class GraphResult:
    """A graph view plus the status of optional algorithm enrichment."""

    view: GraphView
    algorithm_status: GraphAlgorithmStatus
    graph_version: str


class GraphService:
    """Load a bounded snapshot and enrich it without risking endpoint failure."""

    def __init__(
        self,
        repository: GraphRepository,
        *,
        view_builder: GraphViewBuilder = build_graph_view,
    ) -> None:
        self._repository = repository
        self._view_builder = view_builder

    async def get_graph(self, paper_id: UUID, *, depth: int, limit: int) -> GraphResult | None:
        """Return the requested graph, falling back only if enrichment fails."""
        snapshot = await self._repository.get_ego_graph(
            paper_id,
            depth=depth,
            max_nodes=limit,
        )
        if snapshot is None:
            return None

        try:
            view = self._view_builder(
                center_id=snapshot.center_id,
                nodes=snapshot.nodes,
                citation_edges=list(snapshot.edges),
                keywords_by_paper=None,
                limit=limit,
            )
        except Exception:
            logger.exception(
                "graph_algorithm_failed",
                paper_id=str(paper_id),
                graph_version=GRAPH_VERSION,
            )
            return GraphResult(
                view=_fallback_view(snapshot, limit=limit),
                algorithm_status="fallback",
                graph_version=GRAPH_VERSION,
            )

        return GraphResult(
            view=view,
            algorithm_status="ready",
            graph_version=GRAPH_VERSION,
        )


def _fallback_view(snapshot: GraphSnapshot, *, limit: int) -> GraphView:
    """Keep repository order and raw citation weights in a bounded view."""
    center = snapshot.nodes[snapshot.center_id]
    kept_nodes = [center]
    kept_nodes.extend(
        node for node_id, node in snapshot.nodes.items() if node_id != snapshot.center_id
    )
    kept_nodes = kept_nodes[:limit]
    kept_ids = {node.id for node in kept_nodes}
    kept_edges = tuple(
        edge for edge in snapshot.edges if edge.source in kept_ids and edge.target in kept_ids
    )
    return GraphView(
        center_id=snapshot.center_id,
        nodes=tuple(kept_nodes),
        edges=kept_edges,
    )
