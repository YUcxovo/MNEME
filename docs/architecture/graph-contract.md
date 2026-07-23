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
    async def upsert_papers(self, papers: Sequence[PaperNode]) -> None: ...
    async def upsert_citations(self, edges: Sequence[CitationEdge]) -> None: ...
    async def get_ego_graph(
        self, paper_id: UUID, *, depth: int, max_nodes: int
    ) -> GraphSnapshot: ...
    async def save_algorithm_scores(
        self, graph_version: str, scores: Sequence[NodeScore]
    ) -> None: ...

class GraphAlgorithm(Protocol):
    def weight_edges(self, graph: GraphSnapshot) -> GraphSnapshot: ...
    def cluster_nodes(self, graph: GraphSnapshot) -> GraphSnapshot: ...
    def rank_nodes(self, graph: GraphSnapshot) -> GraphSnapshot: ...
    def select_user_subgraph(
        self, graph: GraphSnapshot, preference: UserPreferenceVector
    ) -> GraphSnapshot: ...
```

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
- The first persisted/public graph version is `citation-graph-v1`. Yifan's algorithm parameters
  remain independently versioned; the interface above is frozen at the end of Milestone 1.
