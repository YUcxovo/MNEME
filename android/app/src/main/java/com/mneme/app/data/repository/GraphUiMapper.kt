package com.mneme.app.data.repository

import com.mneme.app.data.network.GraphDto
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel
import kotlinx.serialization.SerializationException

internal fun GraphDto.toGraphUi(): GraphUiModel {
    val nodeIds = nodes.map { node -> node.id }
    validateNodes(nodeIds)
    validateEdges(nodeIds)
    val status = algorithmStatus.toUiStatus()
    return GraphUiModel(
        centerId = centerId,
        nodes =
            nodes.map { node ->
                GraphNodeUiModel(
                    id = node.id,
                    title = node.title,
                    category = node.category,
                    clusterId = node.clusterId,
                    rankScore = node.rankScore,
                )
            },
        edges =
            edges.map { edge ->
                GraphEdgeUiModel(
                    source = edge.source,
                    target = edge.target,
                    weight = edge.weight,
                )
            },
        algorithmStatus = status,
        graphVersion = graphVersion,
        disclosure = status.disclosure(),
    )
}

private fun GraphDto.validateNodes(nodeIds: List<String>) {
    if (nodeIds.size > GRAPH_CONTRACT_NODE_LIMIT || nodeIds.size != nodeIds.toSet().size) {
        throw SerializationException("The graph exceeds its node limit or contains duplicates.")
    }
    val invalidNode =
        centerId.isBlank() ||
            (nodes.isNotEmpty() && centerId !in nodeIds) ||
            nodes.any { node -> node.id.isBlank() || node.title.isBlank() }
    if (invalidNode) {
        throw SerializationException("The graph contains an invalid center or paper node.")
    }
}

private fun GraphDto.validateEdges(nodeIds: List<String>) {
    if (edges.any { edge -> edge.source !in nodeIds || edge.target !in nodeIds }) {
        throw SerializationException("The graph contains an edge outside its paper nodes.")
    }
}

private fun String.toUiStatus(): GraphAlgorithmUiStatus =
    when (this) {
        "ready" -> GraphAlgorithmUiStatus.READY
        "fallback" -> GraphAlgorithmUiStatus.FALLBACK
        else -> throw SerializationException("The graph has an unknown algorithm status.")
    }

private fun GraphAlgorithmUiStatus.disclosure(): ContentDisclosureUiModel =
    ContentDisclosureUiModel(
        origin = ContentOrigin.LIVE_BACKEND,
        message =
            when (this) {
                GraphAlgorithmUiStatus.READY ->
                    "Citation graph returned by the configured backend."
                GraphAlgorithmUiStatus.FALLBACK ->
                    "Citation graph returned by the backend using its deterministic baseline."
            },
    )

private const val GRAPH_CONTRACT_NODE_LIMIT = 200
