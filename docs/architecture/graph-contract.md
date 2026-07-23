# Knowledge-Graph Contract

The MVP graph is a paper citation graph, not an open-ended entity knowledge graph.

## Ownership Boundary

- Ruiyu: graph tables, repositories, ingestion, baseline citation-edge builder, public
  `/graph/{paper_id}` endpoint, limits, persistence, and operational behavior.
- Yifan: edge weighting, keyword co-occurrence features, clustering, ranking, and
  user-subgraph selection.
- Heng/Hanyang: Android rendering and interaction only.

## Internal Interfaces

```python
class GraphRepository(Protocol):
    async def get_ego_graph(
        self, paper_id: UUID, *, depth: int, max_nodes: int
    ) -> GraphSnapshot | None: ...

def build_graph_view(
    *,
    center_id: UUID,
    nodes: dict[UUID, GraphNode],
    citation_edges: list[GraphEdge],
    keywords_by_paper: dict[UUID, set[str]] | None,
    limit: int,
) -> GraphView: ...
```

Semantic Scholar writes use a separate `CitationGraphRepository.persist_neighbors(...)` boundary because provider identities, collision resolution, and transaction ownership are ingestion concerns rather than public graph-query concerns. The HTTP service calls the pure `build_graph_view` algorithm only after the SQL repository has enforced depth and node bounds. Algorithm results are computed per request in M3 rather than persisted as hidden mutable graph state.

## MVP Constraints and Fallback

- Nodes are papers; edges are citations.
- Citation direction is `source cites target`. Semantic Scholar references therefore produce
  `center -> referenced` edges, while citations produce `citing -> center` edges.
- A persisted edge may temporarily identify either endpoint by a Semantic Scholar paper ID, but
  at least one endpoint must be a local paper. External endpoints are resolved when their paper
  enters the local catalog.
- The public graph contains only locally resolved paper UUIDs. Unresolved observations remain
  persisted for later resolution and are not exposed as fake internal resources.
- Categories and keywords are attributes, not separate concept nodes.
- Default traversal depth is 1; maximum depth is 2.
- Default response limit is 50 nodes; hard maximum is 200.
- If Yifan's algorithm is unavailable or fails, return the baseline citation graph with
  deterministic chronological ordering and `algorithm_status: "fallback"`.
- The first public graph version is `citation-graph-v1`. Yifan's algorithm parameters
  remain independently versioned; the interface above is frozen at the end of Milestone 1.
