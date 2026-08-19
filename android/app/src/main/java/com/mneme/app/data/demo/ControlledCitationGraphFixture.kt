package com.mneme.app.data.demo

import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel

object ControlledCitationGraphFixture {
    private const val UUID_SUFFIX_WIDTH = 12
    const val PRIMARY_NEIGHBOR_ID = "00000000-0000-4000-8000-000000000001"
    const val DEEP_NEIGHBOR_ID = "00000000-0000-4000-8000-000000000011"
    const val NODE_COUNT = 12
    const val EDGE_COUNT = 18

    private val paperSpecs =
        listOf(
            ControlledPaperSpec(
                PRIMARY_NEIGHBOR_ID,
                "Attention predecessor",
                "cs.CL",
                "attention",
                0.92,
            ),
            ControlledPaperSpec(
                nodeId(2),
                "Encoder study",
                "cs.LG",
                "attention",
                0.84,
            ),
            ControlledPaperSpec(
                nodeId(3),
                "Retrieval study",
                "cs.IR",
                "retrieval",
                0.78,
            ),
            ControlledPaperSpec(
                nodeId(4),
                "Evaluation study",
                "cs.AI",
                "evaluation",
                0.73,
            ),
            ControlledPaperSpec(
                nodeId(5),
                "Efficient transformers",
                "cs.LG",
                "attention",
                0.68,
            ),
            ControlledPaperSpec(
                nodeId(6),
                "Multilingual models",
                "cs.CL",
                "language",
                0.62,
            ),
            ControlledPaperSpec(
                nodeId(7),
                "Dense retrieval",
                "cs.IR",
                "retrieval",
                0.57,
            ),
            ControlledPaperSpec(
                nodeId(8),
                "Graph retrieval",
                "cs.IR",
                "retrieval",
                0.52,
            ),
            ControlledPaperSpec(
                nodeId(9),
                "Robustness study",
                "stat.ML",
                "evaluation",
                0.47,
            ),
            ControlledPaperSpec(
                nodeId(10),
                "Benchmark study",
                "cs.AI",
                "evaluation",
                0.41,
            ),
            ControlledPaperSpec(
                DEEP_NEIGHBOR_ID,
                "Systems study",
                "cs.DC",
                null,
                null,
            ),
        )

    private val papers =
        paperSpecs.associate { spec ->
            spec.id to
                PaperUiModel(
                    id = spec.id,
                    title = spec.title,
                    authors = "Repository graph fixture",
                    category = spec.category,
                    summary =
                        "This synthetic paper exists only to test bounded citation-graph rendering.",
                )
        }

    fun paperDetail(
        paperId: String,
        disclosure: ContentDisclosureUiModel,
    ): PaperDetailUiModel? =
        papers[paperId]?.let { paper ->
            PaperDetailUiModel(
                paper = paper,
                disclosure = disclosure,
                abstractText =
                    "This repository-controlled node exercises graph selection and navigation. " +
                        "It does not describe a real publication or citation.",
                keyClaims = emptyList(),
                methodology = null,
                limitation = "Use the live backend for real paper metadata and citation data.",
                sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
                source =
                    SourceUiModel(
                        label = "No external source in the controlled graph fixture",
                        location = "Android renderer fixture",
                        url = "https://arxiv.org/",
                        matchStatus = SourceMatchUiStatus.NOT_CHECKED,
                    ),
            )
        }

    fun graph(
        centerPaper: PaperUiModel,
        disclosure: ContentDisclosureUiModel,
    ): GraphUiModel =
        GraphUiModel(
            centerId = centerPaper.id,
            nodes =
                listOf(
                    GraphNodeUiModel(
                        id = centerPaper.id,
                        title = centerPaper.title,
                        category = centerPaper.category,
                        clusterId = "attention",
                        rankScore = 1.0,
                    ),
                ) +
                    paperSpecs.map { spec ->
                        GraphNodeUiModel(
                            id = spec.id,
                            title = spec.title,
                            category = spec.category,
                            clusterId = spec.clusterId,
                            rankScore = spec.rankScore,
                        )
                    },
            edges = controlledEdges(centerPaper.id),
            algorithmStatus = GraphAlgorithmUiStatus.FALLBACK,
            graphVersion = "controlled-renderer-fixture-v2",
            disclosure =
                disclosure.copy(
                    message =
                        "Controlled renderer fixture with $NODE_COUNT synthetic nodes and " +
                            "$EDGE_COUNT synthetic edges. It is not a claim about real citations.",
                ),
        )

    @Suppress("MagicNumber")
    private fun controlledEdges(centerId: String): List<GraphEdgeUiModel> =
        listOf(
            edge(centerId, 1, 0.93),
            edge(centerId, 2, 0.86),
            edge(centerId, 3, 0.79),
            edge(centerId, 4, 0.71),
            edge(5, centerId, 0.89),
            edge(5, 1, 0.68),
            edge(5, 2, 0.63),
            edge(6, centerId, 0.82),
            edge(6, 1, 0.59),
            edge(7, 3, 0.76),
            edge(7, centerId, 0.64),
            edge(8, 3, 0.72),
            edge(8, 7, 0.55),
            edge(9, centerId, 0.67),
            edge(9, 4, 0.61),
            edge(10, 4, 0.74),
            edge(10, 9, 0.52),
            edge(11, 5, 0.48),
        )

    private fun edge(
        source: Int,
        target: Int,
        weight: Double,
    ): GraphEdgeUiModel = edge(nodeId(source), nodeId(target), weight)

    private fun edge(
        source: String,
        target: Int,
        weight: Double,
    ): GraphEdgeUiModel = edge(source, nodeId(target), weight)

    private fun edge(
        source: Int,
        target: String,
        weight: Double,
    ): GraphEdgeUiModel = edge(nodeId(source), target, weight)

    private fun edge(
        source: String,
        target: String,
        weight: Double,
    ): GraphEdgeUiModel = GraphEdgeUiModel(source = source, target = target, weight = weight)

    private fun nodeId(index: Int): String {
        val suffix = index.toString().padStart(UUID_SUFFIX_WIDTH, '0')
        return "00000000-0000-4000-8000-$suffix"
    }

    private data class ControlledPaperSpec(
        val id: String,
        val title: String,
        val category: String,
        val clusterId: String?,
        val rankScore: Double?,
    )
}
