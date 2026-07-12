package com.mneme.app.ui.model

data class PaperUiModel(
    val id: String,
    val title: String,
    val authors: String,
    val category: String,
    val summary: String,
)

data class DigestUiModel(
    val id: String,
    val title: String,
    val summary: String,
    val dateLabel: String,
)
