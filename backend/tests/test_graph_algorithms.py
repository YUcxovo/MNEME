"""Knowledge-graph algorithms: weighting, clustering, ranking, selection."""

from uuid import UUID

import pytest

from mneme.graph import (
    GraphEdge,
    GraphNode,
    build_graph_view,
    extract_keywords,
    keyword_cooccurrence_edges,
    label_propagation_clusters,
    rank_nodes,
    select_subgraph,
    weight_citation_edges,
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _node(value: int, title: str = "Paper") -> GraphNode:
    return GraphNode(id=_uuid(value), title=f"{title} {value}", category="cs.AI")


@pytest.mark.base
def test_keywords_come_from_title_and_categories_without_stopwords() -> None:
    keywords = extract_keywords("Attention is all you need for the win", ["cs.CL"])

    assert "attention" in keywords
    assert "cs.cl" in keywords
    assert "the" not in keywords


@pytest.mark.base
def test_cooccurrence_edges_use_jaccard_and_drop_weak_pairs() -> None:
    keywords = {
        _uuid(1): {"attention", "transformer", "translation"},
        _uuid(2): {"attention", "transformer", "vision"},
        _uuid(3): {"quantum", "chemistry", "simulation"},
    }

    edges = keyword_cooccurrence_edges(keywords)

    assert len(edges) == 1
    edge = edges[0]
    assert {edge.source, edge.target} == {_uuid(1), _uuid(2)}
    assert edge.weight == pytest.approx(2 / 4)


@pytest.mark.base
def test_citation_weights_damp_highly_cited_targets() -> None:
    hub = _uuid(9)
    edges = [GraphEdge(source=_uuid(index), target=hub) for index in range(1, 7)]
    edges.append(GraphEdge(source=_uuid(1), target=_uuid(8)))

    weighted = weight_citation_edges(edges)

    hub_weight = next(edge.weight for edge in weighted if edge.target == hub)
    leaf_weight = next(edge.weight for edge in weighted if edge.target == _uuid(8))
    assert hub_weight is not None and leaf_weight is not None
    assert hub_weight < leaf_weight


@pytest.mark.base
def test_label_propagation_finds_two_communities() -> None:
    community_a = [_uuid(1), _uuid(2), _uuid(3)]
    community_b = [_uuid(4), _uuid(5), _uuid(6)]
    edges = [
        GraphEdge(source=community_a[0], target=community_a[1], weight=1.0),
        GraphEdge(source=community_a[1], target=community_a[2], weight=1.0),
        GraphEdge(source=community_a[0], target=community_a[2], weight=1.0),
        GraphEdge(source=community_b[0], target=community_b[1], weight=1.0),
        GraphEdge(source=community_b[1], target=community_b[2], weight=1.0),
        GraphEdge(source=community_b[0], target=community_b[2], weight=1.0),
        GraphEdge(source=community_a[2], target=community_b[0], weight=0.05),
    ]

    labels = label_propagation_clusters(community_a + community_b, edges)

    assert len({labels[node] for node in community_a}) == 1
    assert len({labels[node] for node in community_b}) == 1
    assert labels[community_a[0]] != labels[community_b[0]]


@pytest.mark.base
def test_rank_scores_normalize_to_unit_interval() -> None:
    nodes = [_uuid(1), _uuid(2), _uuid(3)]
    edges = [
        GraphEdge(source=_uuid(1), target=_uuid(2), weight=1.0),
        GraphEdge(source=_uuid(1), target=_uuid(3), weight=1.0),
    ]

    ranks = rank_nodes(nodes, edges)

    assert ranks[_uuid(1)] == 1.0
    assert 0 < ranks[_uuid(2)] < 1.0


@pytest.mark.base
def test_subgraph_selection_prefers_strong_edges_under_a_limit() -> None:
    center = _uuid(1)
    strong = _uuid(2)
    weak = _uuid(3)
    edges = [
        GraphEdge(source=center, target=strong, weight=0.9),
        GraphEdge(source=center, target=weak, weight=0.1),
    ]

    selected = select_subgraph(seeds=[center], edges=edges, limit=2)

    assert selected == {center, strong}


@pytest.mark.base
def test_graph_view_is_bounded_scored_and_clustered() -> None:
    nodes = {node.id: node for node in [_node(1), _node(2), _node(3), _node(4)]}
    citation_edges = [
        GraphEdge(source=_uuid(1), target=_uuid(2)),
        GraphEdge(source=_uuid(2), target=_uuid(3)),
        GraphEdge(source=_uuid(1), target=_uuid(4)),
    ]

    view = build_graph_view(
        center_id=_uuid(1),
        nodes=nodes,
        citation_edges=citation_edges,
        keywords_by_paper={
            _uuid(1): {"attention"},
            _uuid(2): {"attention"},
            _uuid(3): {"quantum"},
            _uuid(4): {"attention", "vision"},
        },
        limit=3,
    )

    assert len(view.nodes) <= 3
    assert view.center_id == _uuid(1)
    assert any(node.id == _uuid(1) for node in view.nodes)
    kept_ids = {node.id for node in view.nodes}
    for edge in view.edges:
        assert edge.source in kept_ids and edge.target in kept_ids
    for node in view.nodes:
        assert node.cluster_id is not None
        assert node.rank_score is not None


@pytest.mark.base
def test_graph_view_is_deterministic() -> None:
    nodes = {node.id: node for node in [_node(1), _node(2), _node(3)]}
    edges = [
        GraphEdge(source=_uuid(1), target=_uuid(2)),
        GraphEdge(source=_uuid(2), target=_uuid(3)),
    ]

    first = build_graph_view(center_id=_uuid(1), nodes=nodes, citation_edges=edges, limit=10)
    second = build_graph_view(center_id=_uuid(1), nodes=nodes, citation_edges=edges, limit=10)

    assert first == second
