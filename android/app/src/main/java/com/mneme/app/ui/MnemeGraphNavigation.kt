package com.mneme.app.ui

import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.mneme.app.ui.navigation.GraphRoute
import com.mneme.app.ui.navigation.PaperDetailRoute

internal fun NavGraphBuilder.graphNavigation(
    navController: NavHostController,
    state: GraphUiState,
    requestGraph: (String) -> Unit,
    retryGraph: (String) -> Unit,
) {
    composable<GraphRoute> { entry ->
        val paperId = entry.toRoute<GraphRoute>().paperId
        LaunchedEffect(paperId) { requestGraph(paperId) }
        GraphDestination(
            paperId = paperId,
            state = state,
            onRetry = { retryGraph(paperId) },
            onOpenPaper = { selectedPaperId ->
                navController.navigate(PaperDetailRoute(selectedPaperId))
            },
        )
    }
}
