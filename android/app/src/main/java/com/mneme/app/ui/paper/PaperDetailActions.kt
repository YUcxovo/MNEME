package com.mneme.app.ui.paper

data class PaperDetailActions(
    val askQuestion: () -> Unit,
    val exploreGraph: () -> Unit,
    val savePaper: () -> Unit,
    val sharePaper: () -> Unit,
    val openSource: (String) -> Unit,
)
