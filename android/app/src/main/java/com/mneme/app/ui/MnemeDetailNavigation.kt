package com.mneme.app.ui

import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.mneme.app.ui.navigation.GraphRoute
import com.mneme.app.ui.navigation.PaperDeepLink
import com.mneme.app.ui.navigation.PaperDetailRoute
import com.mneme.app.ui.navigation.QaRoute

internal fun NavGraphBuilder.paperDetailNavigation(
    navController: NavHostController,
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    externalActions: MnemeExternalActions,
) {
    composable<PaperDetailRoute> { entry ->
        val route = entry.toRoute<PaperDetailRoute>()
        val paperId = route.paperId
        LaunchedEffect(paperId) { actions.requestPaper(paperId) }
        LaunchedEffect(route.externalRequestId, paperId, snapshot.paper) {
            val requestId = route.externalRequestId ?: return@LaunchedEffect
            val loadedPaper =
                (snapshot.paper as? PaperDetailUiState.Content)
                    ?.paper
                    ?.paper
                    ?.takeIf { it.id == paperId }
                    ?: return@LaunchedEffect
            val recordedKey = "external-paper-opened-$requestId"
            if (entry.savedStateHandle.get<Boolean>(recordedKey) != true) {
                entry.savedStateHandle[recordedKey] = true
                actions.recordPaperOpened(loadedPaper.id)
            }
        }
        paperDestination(
            paperId = paperId,
            state = snapshot.paper,
            saveStatus = snapshot.engagement.saveStatus(paperId),
            shareStatus = snapshot.engagement.shareStatus(paperId),
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
        qaDestination(
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
    val shareText =
        PaperDeepLink.buildShareText(
            title = paper.paper.title,
            paperId = paper.paper.id,
            arxivUrl = paper.source.url,
        )
    externalActions.sharePaper(paper.paper.title, shareText)
    actions.sharePaper(paperId)
}
