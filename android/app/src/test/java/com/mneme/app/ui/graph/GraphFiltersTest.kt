package com.mneme.app.ui.graph

import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel
import org.junit.Assert.assertEquals
import org.junit.Test

class GraphFiltersTest {
    @Test
    fun relationAndCategoryFilters_keepOnlyRealDirectedNeighbors() {
        val graph = fixtureGraph()

        assertEquals(
            listOf("center", "reference"),
            graph.filteredCitationGraph(GraphRelationFilter.REFERENCES, null).nodes.map(GraphNodeUiModel::id),
        )
        assertEquals(
            listOf("center", "citation"),
            graph.filteredCitationGraph(GraphRelationFilter.CITATIONS, null).nodes.map(GraphNodeUiModel::id),
        )
        assertEquals(
            listOf("center", "reference"),
            graph.filteredCitationGraph(GraphRelationFilter.ALL, "cs.AI").nodes.map(GraphNodeUiModel::id),
        )
        assertEquals(listOf("cs.AI", "cs.CL"), graph.availableCategories())
    }

    private fun fixtureGraph() =
        GraphUiModel(
            centerId = "center",
            nodes =
                listOf(
                    node("center", "cs.AI"),
                    node("reference", "cs.AI"),
                    node("citation", "cs.CL"),
                    node("unknown", null),
                ),
            edges =
                listOf(
                    GraphEdgeUiModel("center", "reference", null),
                    GraphEdgeUiModel("citation", "center", null),
                    GraphEdgeUiModel("unknown", "reference", null),
                ),
            algorithmStatus = GraphAlgorithmUiStatus.READY,
            graphVersion = "citation-graph-v1",
            disclosure = ContentDisclosureUiModel(ContentOrigin.LIVE_BACKEND, "Live"),
        )

    private fun node(
        id: String,
        category: String?,
    ) = GraphNodeUiModel(id, id, category, null, null)
}
