package com.mneme.app.ui.navigation

import kotlinx.serialization.Serializable

@Serializable
data object BriefingRoute

@Serializable
data object SavedRoute

@Serializable
data object InterestsRoute

@Serializable
data class PaperDetailRoute(
    val paperId: String,
    val externalRequestId: Long? = null,
)

@Serializable
data class QaRoute(
    val paperId: String,
)

@Serializable
data class GraphRoute(
    val paperId: String,
)
