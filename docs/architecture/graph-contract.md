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
- Categories and keywords are attributes, not separate concept nodes.
- Default traversal depth is 1; maximum depth is 2.
- Default response limit is 50 nodes; hard maximum is 200.
- If Yifan's algorithm is unavailable or fails, return the baseline citation graph with
  deterministic chronological ordering and `algorithm_status: "fallback"`.
- Algorithm parameters and scoring formulas are deferred until Milestone 3 and versioned
  with `graph_version`; the interface above is frozen at the end of Milestone 1.
