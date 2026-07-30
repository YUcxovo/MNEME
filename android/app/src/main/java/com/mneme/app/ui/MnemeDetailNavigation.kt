package com.mneme.app.ui

import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.mneme.app.ui.navigation.GraphRoute
import com.mneme.app.ui.navigation.PaperDetailRoute
import com.mneme.app.ui.navigation.QaRoute

internal fun NavGraphBuilder.paperDetailNavigation(
    navController: NavHostController,
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    externalActions: MnemeExternalActions,
) {
    composable<PaperDetailRoute> { entry ->
        val paperId = entry.toRoute<PaperDetailRoute>().paperId
        LaunchedEffect(paperId) { actions.requestPaper(paperId) }
        PaperDestination(
            paperId = paperId,
            state = snapshot.paper,
            isSaved = paperId in snapshot.savedPaperIds,
            actions =
                PaperDestinationActions(
                    retry = { actions.retryPaper(paperId) },
                    askQuestion = { navController.navigate(QaRoute(paperId)) },
                    exploreGraph = { navController.navigate(GraphRoute(paperId)) },
                    savePaper = { actions.savePaper(paperId) },
                    sharePaper = {
                        shareCurrentPaper(
                            paperId = paperId,
                            state = snapshot.paper,
                            actions = actions,
                            externalActions = externalActions,
                        )
                    },
                    openSource = externalActions.openSource,
                ),
        )
    }
}

internal fun NavGraphBuilder.qaNavigation(
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    externalActions: MnemeExternalActions,
) {
    composable<QaRoute> { entry ->
        val paperId = entry.toRoute<QaRoute>().paperId
        LaunchedEffect(paperId) { actions.openQa(paperId) }
        QaDestination(
            paperId = paperId,
            state = snapshot.qa,
            onSubmit = { question -> actions.requestQa(paperId, question) },
            onOpenSource = externalActions.openSource,
        )
    }
}

private fun shareCurrentPaper(
    paperId: String,
    state: PaperDetailUiState,
    actions: MnemeUiActions,
    externalActions: MnemeExternalActions,
) {
    val paper =
        (state as? PaperDetailUiState.Content)
            ?.paper
            ?.takeIf { it.paper.id == paperId }
            ?: return
    externalActions.sharePaper(paper.paper.title, paper.source.url)
    actions.sharePaper(paperId)
}
