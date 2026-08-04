package com.mneme.app.ui.graph

import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel

enum class GraphRelationFilter {
    ALL,
    REFERENCES,
    CITATIONS,
}

internal data class FilteredCitationGraph(
    val nodes: List<GraphNodeUiModel>,
    val edges: List<GraphEdgeUiModel>,
)

internal fun GraphUiModel.filteredCitationGraph(
    relation: GraphRelationFilter,
    category: String?,
): FilteredCitationGraph {
    val relationEdges =
        when (relation) {
            GraphRelationFilter.ALL -> edges
            GraphRelationFilter.REFERENCES -> edges.filter { it.source == centerId }
            GraphRelationFilter.CITATIONS -> edges.filter { it.target == centerId }
        }
    val allowedIds = relationEdges.flatMapTo(mutableSetOf()) { listOf(it.source, it.target) }.apply { add(centerId) }
    val visibleNodes =
        nodes.filter { node ->
            node.id in allowedIds && (node.id == centerId || category == null || node.category == category)
        }
    val visibleIds = visibleNodes.mapTo(mutableSetOf()) { it.id }
    return FilteredCitationGraph(
        nodes = visibleNodes,
        edges = relationEdges.filter { it.source in visibleIds && it.target in visibleIds },
    )
}

internal fun GraphUiModel.availableCategories(): List<String> =
    nodes
        .mapNotNull(GraphNodeUiModel::category)
        .filter(String::isNotBlank)
        .distinct()
        .sorted()
