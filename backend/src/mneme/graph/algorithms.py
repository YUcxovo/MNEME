"""Pure knowledge-graph algorithms over citation and keyword data.

All functions are deterministic and side-effect free: they take plain node
and edge values from Ruiyu's graph framework and return scored, clustered,
bounded views matching the frozen ``Graph`` contract. No database access
happens here, so every algorithm is unit-testable in isolation.
"""

import math
import re
from collections import defaultdict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_WORD = re.compile(r"[a-z0-9][a-z0-9-]{2,}")
_STOPWORDS = frozenset(
    [
        "and",
        "are",
        "for",
        "from",
        "has",
        "have",
        "its",
        "not",
        "the",
        "this",
        "via",
        "with",
        "without",
        "using",
        "toward",
        "towards",
        "into",
        "over",
        "under",
        "between",
        "about",
        "their",
        "them",
        "then",
        "than",
        "when",
        "where",
        "which",
        "while",
        "what",
        "does",
        "can",
        "could",
        "should",
        "would",
        "all",
        "any",
        "our",
        "your",
        "new",
    ]
)

_MIN_COOCCURRENCE_WEIGHT = 0.1
_MAX_CLUSTER_ROUNDS = 10


class GraphNode(BaseModel):
    """One paper node enriched with algorithm outputs."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    title: str
    category: str | None = None
    cluster_id: str | None = None
    rank_score: float | None = Field(default=None, ge=0, le=1)


class GraphEdge(BaseModel):
    """One directed edge with an optional algorithm weight."""

    model_config = ConfigDict(frozen=True)

    source: UUID
    target: UUID
    weight: float | None = Field(default=None, ge=0)


class GraphView(BaseModel):
    """A bounded, scored, clustered subgraph ready for the API contract."""

    model_config = ConfigDict(frozen=True)

    center_id: UUID
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def extract_keywords(title: str, categories: list[str]) -> set[str]:
    """Keyword set from a title and arXiv categories for co-occurrence."""
    words = {word for word in _WORD.findall(title.casefold()) if word not in _STOPWORDS}
    return words | {category.casefold() for category in categories}


def keyword_cooccurrence_edges(keywords_by_paper: dict[UUID, set[str]]) -> list[GraphEdge]:
    """Undirected co-occurrence edges (emitted once per pair) by Jaccard.

    Pairs below the minimum weight are dropped so dense category overlap
    does not turn the graph into a clique.
    """
    papers = sorted(keywords_by_paper, key=str)
    edges: list[GraphEdge] = []
    for index, source in enumerate(papers):
        source_keywords = keywords_by_paper[source]
        if not source_keywords:
            continue
        for target in papers[index + 1 :]:
            target_keywords = keywords_by_paper[target]
            if not target_keywords:
                continue
            union = source_keywords | target_keywords
            weight = len(source_keywords & target_keywords) / len(union)
            if weight >= _MIN_COOCCURRENCE_WEIGHT:
                edges.append(GraphEdge(source=source, target=target, weight=round(weight, 6)))
    return edges


def weight_citation_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    """Weight citation edges by damping highly cited targets.

    ``1 / log2(2 + in_degree(target))`` keeps edges into ubiquitous papers
    from dominating layout and ranking.
    """
    in_degrees: dict[UUID, int] = defaultdict(int)
    for edge in edges:
        in_degrees[edge.target] += 1
    return [
        GraphEdge(
            source=edge.source,
            target=edge.target,
            weight=round(1.0 / math.log2(2 + in_degrees[edge.target]), 6),
        )
        for edge in edges
    ]


def _adjacency(edges: list[GraphEdge]) -> dict[UUID, list[tuple[UUID, float]]]:
    adjacency: dict[UUID, list[tuple[UUID, float]]] = defaultdict(list)
    for edge in edges:
        weight = edge.weight if edge.weight is not None else 1.0
        adjacency[edge.source].append((edge.target, weight))
        adjacency[edge.target].append((edge.source, weight))
    return adjacency


def label_propagation_clusters(node_ids: list[UUID], edges: list[GraphEdge]) -> dict[UUID, str]:
    """Deterministic weighted label propagation.

    Nodes are visited in sorted order and ties break on the smallest label,
    so identical inputs always produce identical clusters. Converges or
    stops after a bounded number of rounds.
    """
    labels: dict[UUID, str] = {node_id: str(node_id) for node_id in node_ids}
    adjacency = _adjacency(edges)
    ordered = sorted(node_ids, key=str)

    for _ in range(_MAX_CLUSTER_ROUNDS):
        changed = False
        for node_id in ordered:
            neighbor_weights: dict[str, float] = defaultdict(float)
            for neighbor, weight in adjacency.get(node_id, ()):
                if neighbor in labels:
                    neighbor_weights[labels[neighbor]] += weight
            if not neighbor_weights:
                continue
            best_label = min(
                neighbor_weights,
                key=lambda label: (-neighbor_weights[label], label),
            )
            if best_label != labels[node_id]:
                labels[node_id] = best_label
                changed = True
        if not changed:
            break
    return labels


def rank_nodes(node_ids: list[UUID], edges: list[GraphEdge]) -> dict[UUID, float]:
    """Weighted degree centrality normalized to [0, 1]."""
    adjacency = _adjacency(edges)
    raw = {node_id: sum(weight for _, weight in adjacency.get(node_id, ())) for node_id in node_ids}
    maximum = max(raw.values(), default=0.0)
    if maximum == 0:
        return {node_id: 0.0 for node_id in node_ids}
    return {node_id: round(value / maximum, 6) for node_id, value in raw.items()}


def select_subgraph(*, seeds: list[UUID], edges: list[GraphEdge], limit: int) -> set[UUID]:
    """Bounded best-first expansion from seed nodes.

    The frontier prefers strong edges, so the selected subgraph keeps the
    most relevant neighborhood when the limit truncates it. Used both for
    paper-centered graphs (one seed) and user subgraphs (papers the user
    engaged with as seeds).
    """
    if limit <= 0:
        return set()
    adjacency = _adjacency(edges)
    selected: set[UUID] = set()
    frontier: list[tuple[float, str, UUID]] = [
        (1.0, str(seed), seed) for seed in sorted(seeds, key=str)
    ]
    seen: set[UUID] = set(seeds)

    while frontier and len(selected) < limit:
        frontier.sort(key=lambda item: (-item[0], item[1]))
        strength, _, node_id = frontier.pop(0)
        selected.add(node_id)
        for neighbor, weight in sorted(
            adjacency.get(node_id, ()), key=lambda item: (-item[1], str(item[0]))
        ):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append((strength * weight, str(neighbor), neighbor))
    return selected


def build_graph_view(
    *,
    center_id: UUID,
    nodes: dict[UUID, GraphNode],
    citation_edges: list[GraphEdge],
    keywords_by_paper: dict[UUID, set[str]] | None = None,
    limit: int,
) -> GraphView:
    """Produce the bounded, weighted, clustered view for one center paper.

    Citation edges are hub-damped; optional keyword co-occurrence edges add
    topical connections; the subgraph is selected best-first from the
    center; surviving nodes get cluster ids and rank scores.
    """
    weighted = weight_citation_edges(citation_edges)
    if keywords_by_paper:
        weighted.extend(keyword_cooccurrence_edges(keywords_by_paper))

    kept_ids = select_subgraph(seeds=[center_id], edges=weighted, limit=limit)
    kept_ids &= set(nodes)
    kept_ids.add(center_id)

    kept_edges = tuple(
        edge for edge in weighted if edge.source in kept_ids and edge.target in kept_ids
    )
    ordered_ids = sorted(kept_ids, key=str)
    clusters = label_propagation_clusters(ordered_ids, list(kept_edges))
    ranks = rank_nodes(ordered_ids, list(kept_edges))

    enriched = tuple(
        nodes[node_id].model_copy(
            update={"cluster_id": clusters.get(node_id), "rank_score": ranks.get(node_id)}
        )
        for node_id in ordered_ids
        if node_id in nodes
    )
    return GraphView(center_id=center_id, nodes=enriched, edges=kept_edges)
