"""Transport-neutral contracts between graph persistence and algorithms."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from mneme.graph.algorithms import GraphEdge, GraphNode


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """One bounded, locally resolved citation neighborhood."""

    center_id: UUID
    nodes: dict[UUID, GraphNode]
    edges: tuple[GraphEdge, ...]


class GraphRepository(Protocol):
    """Database boundary required by the public graph service."""

    async def get_ego_graph(
        self, paper_id: UUID, *, depth: int, max_nodes: int
    ) -> GraphSnapshot | None: ...
