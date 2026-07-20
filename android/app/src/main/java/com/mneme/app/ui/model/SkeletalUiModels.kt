package com.mneme.app.ui.model

data class BriefingUiModel(
    val digest: DigestUiModel,
    val disclosure: String,
    val interests: List<String>,
    val papers: List<PaperUiModel>,
)

data class PaperDetailUiModel(
    val paper: PaperUiModel,
    val disclosure: String,
    val abstractText: String,
    val keyClaims: List<String>,
    val methodology: String,
    val limitation: String,
    val source: SourceUiModel,
)

data class QaUiModel(
    val paperId: String,
    val question: String,
    val answer: String,
    val disclosure: String,
    val source: SourceUiModel,
)

data class SourceUiModel(
    val label: String,
    val location: String,
    val url: String,
)
