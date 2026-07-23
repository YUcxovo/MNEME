"""Frozen v0.1 citation-graph response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from mneme.services.graph import GraphResult


class GraphNode(BaseModel):
    """One paper node with optional graph-algorithm annotations."""

    id: UUID
    title: str
    category: str | None = None
    cluster_id: str | None = None
    rank_score: float | None = Field(default=None, ge=0, le=1)


class GraphEdge(BaseModel):
    """One directed citation edge."""

    source: UUID
    target: UUID
    weight: float | None = Field(default=None, ge=0)


class Graph(BaseModel):
    """A bounded paper-centered citation graph."""

    center_id: UUID
    nodes: list[GraphNode] = Field(max_length=200)
    edges: list[GraphEdge]
    algorithm_status: Literal["ready", "fallback"]
    graph_version: str | None = None

    @classmethod
    def from_result(cls, result: GraphResult) -> "Graph":
        """Map a transport-neutral graph result to the public contract."""
        return cls(
            center_id=result.view.center_id,
            nodes=[
                GraphNode(
                    id=node.id,
                    title=node.title,
                    category=node.category,
                    cluster_id=node.cluster_id,
                    rank_score=node.rank_score,
                )
                for node in result.view.nodes
            ],
            edges=[
                GraphEdge(source=edge.source, target=edge.target, weight=edge.weight)
                for edge in result.view.edges
            ],
            algorithm_status=result.algorithm_status,
            graph_version=result.graph_version,
        )
