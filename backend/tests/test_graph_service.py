"""Tests for public graph assembly and its deterministic fallback."""

import asyncio
from uuid import UUID

import pytest

from mneme.graph.algorithms import GraphEdge, GraphNode, GraphView
from mneme.graph.contracts import GraphSnapshot
from mneme.services.graph import GRAPH_VERSION, GraphService

CENTER_ID = UUID("00000000-0000-0000-0000-000000000001")
NEIGHBOR_ID = UUID("00000000-0000-0000-0000-000000000002")
EXTRA_ID = UUID("00000000-0000-0000-0000-000000000003")


class FakeGraphRepository:
    def __init__(self, snapshot: GraphSnapshot | None) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[UUID, int, int]] = []

    async def get_ego_graph(
        self, paper_id: UUID, *, depth: int, max_nodes: int
    ) -> GraphSnapshot | None:
        self.calls.append((paper_id, depth, max_nodes))
        return self.snapshot


def _snapshot() -> GraphSnapshot:
    return GraphSnapshot(
        center_id=CENTER_ID,
        nodes={
            NEIGHBOR_ID: GraphNode(id=NEIGHBOR_ID, title="Neighbor"),
            CENTER_ID: GraphNode(id=CENTER_ID, title="Center"),
            EXTRA_ID: GraphNode(id=EXTRA_ID, title="Extra"),
        },
        edges=(
            GraphEdge(source=CENTER_ID, target=NEIGHBOR_ID, weight=0.7),
            GraphEdge(source=NEIGHBOR_ID, target=EXTRA_ID, weight=0.5),
        ),
    )


@pytest.mark.base
def test_graph_service_returns_enriched_view() -> None:
    repository = FakeGraphRepository(_snapshot())
    expected = GraphView(
        center_id=CENTER_ID,
        nodes=(GraphNode(id=CENTER_ID, title="Enriched", rank_score=1),),
        edges=(),
    )
    calls: list[dict[str, object]] = []

    def builder(**kwargs: object) -> GraphView:
        calls.append(kwargs)
        return expected

    result = asyncio.run(
        GraphService(repository, view_builder=builder).get_graph(
            CENTER_ID,
            depth=2,
            limit=2,
        )
    )

    assert result is not None
    assert result.view == expected
    assert result.algorithm_status == "ready"
    assert result.graph_version == GRAPH_VERSION
    assert repository.calls == [(CENTER_ID, 2, 2)]
    assert calls[0]["center_id"] == CENTER_ID
    assert calls[0]["keywords_by_paper"] is None
    assert calls[0]["limit"] == 2


@pytest.mark.base
def test_graph_service_falls_back_to_bounded_raw_graph() -> None:
    repository = FakeGraphRepository(_snapshot())

    def broken_builder(**_kwargs: object) -> GraphView:
        raise RuntimeError("algorithm unavailable")

    result = asyncio.run(
        GraphService(repository, view_builder=broken_builder).get_graph(
            CENTER_ID,
            depth=1,
            limit=2,
        )
    )

    assert result is not None
    assert result.algorithm_status == "fallback"
    assert [node.id for node in result.view.nodes] == [CENTER_ID, NEIGHBOR_ID]
    assert result.view.edges == (GraphEdge(source=CENTER_ID, target=NEIGHBOR_ID, weight=0.7),)


@pytest.mark.base
def test_graph_service_preserves_missing_paper_result() -> None:
    repository = FakeGraphRepository(None)

    result = asyncio.run(GraphService(repository).get_graph(CENTER_ID, depth=1, limit=50))

    assert result is None
    assert repository.calls == [(CENTER_ID, 1, 50)]
