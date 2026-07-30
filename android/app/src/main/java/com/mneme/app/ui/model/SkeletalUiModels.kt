package com.mneme.app.ui.model

data class BriefingUiModel(
    val digest: DigestUiModel,
    val disclosure: ContentDisclosureUiModel,
    val interests: List<String>,
    val papers: List<PaperUiModel>,
)

data class PaperDetailUiModel(
    val paper: PaperUiModel,
    val disclosure: ContentDisclosureUiModel,
    val abstractText: String,
    val keyClaims: List<String>,
    val methodology: String?,
    val limitation: String?,
    val sourceMatchStatus: SourceMatchUiStatus,
    val source: SourceUiModel,
)

data class QaUiModel(
    val paperId: String,
    val conversationId: String,
    val question: String,
    val answer: String,
    val disclosure: ContentDisclosureUiModel,
    val sourceMatchStatus: SourceMatchUiStatus,
    val sources: List<SourceUiModel>,
)

data class GraphUiModel(
    val centerId: String,
    val nodes: List<GraphNodeUiModel>,
    val edges: List<GraphEdgeUiModel>,
    val algorithmStatus: GraphAlgorithmUiStatus,
    val graphVersion: String?,
    val disclosure: ContentDisclosureUiModel,
)

data class GraphNodeUiModel(
    val id: String,
    val title: String,
    val category: String?,
    val clusterId: String?,
    val rankScore: Double?,
)

data class GraphEdgeUiModel(
    val source: String,
    val target: String,
    val weight: Double?,
)

enum class GraphAlgorithmUiStatus {
    READY,
    FALLBACK,
}

data class SourceUiModel(
    val label: String,
    val location: String,
    val url: String,
    val matchStatus: SourceMatchUiStatus? = null,
)

data class ContentDisclosureUiModel(
    val origin: ContentOrigin,
    val message: String,
)

enum class ContentOrigin {
    LIVE_BACKEND,
    CACHED_BACKEND,
    CONTROLLED_FIXTURE,
}

enum class SourceMatchUiStatus {
    MATCHED,
    PARTIAL,
    NOT_CHECKED,
    INSUFFICIENT_EVIDENCE,
    UNMATCHED,
}
