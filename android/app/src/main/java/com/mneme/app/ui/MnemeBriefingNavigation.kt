package com.mneme.app.ui

import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.mneme.app.ui.home.HomeScreen
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.navigation.BriefingRoute
import com.mneme.app.ui.navigation.PaperDetailRoute

internal fun NavGraphBuilder.briefingNavigation(
    navController: NavHostController,
    state: HomeUiState,
    refreshBriefing: () -> Unit,
    recordPaperImpressions: (List<String>) -> Unit,
    recordPaperOpened: (String) -> Unit,
) {
    composable<BriefingRoute> {
        val briefing = (state as? HomeUiState.Content)?.briefing
        LaunchedEffect(briefing?.digest?.id) {
            briefing?.let { current ->
                recordPaperImpressions(current.papers.map { it.id })
            }
        }
        HomeScreen(
            state = state,
            onRetry = refreshBriefing,
            onPaperClick = { paperId ->
                recordPaperOpened(paperId)
                navController.navigate(PaperDetailRoute(paperId))
            },
        )
    }
}
