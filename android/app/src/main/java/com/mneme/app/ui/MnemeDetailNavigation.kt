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
import com.mneme.app.ui.saved.saveStatus
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay

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
        LaunchedEffect(route.externalRequestId, route.externalEventId, paperId, snapshot.paper) {
            route.externalRequestId ?: return@LaunchedEffect
            val eventId = route.externalEventId ?: return@LaunchedEffect
            val loadedPaper =
                (snapshot.paper as? PaperDetailUiState.Content)
                    ?.paper
                    ?.paper
                    ?.takeIf { it.id == paperId }
                    ?: return@LaunchedEffect
            val recordedKey = "external-paper-opened-$eventId"
            var attempt = 0
            while (
                entry.savedStateHandle.get<Boolean>(recordedKey) != true &&
                attempt < EXTERNAL_EVENT_WRITE_ATTEMPTS
            ) {
                try {
                    if (!actions.recordExternalPaperOpened(eventId, loadedPaper.id)) {
                        return@LaunchedEffect
                    }
                    entry.savedStateHandle[recordedKey] = true
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    attempt += 1
                    if (attempt < EXTERNAL_EVENT_WRITE_ATTEMPTS) {
                        delay(EXTERNAL_EVENT_RETRY_DELAY_MILLIS * attempt)
                    }
                }
            }
        }
        paperDestination(
            paperId = paperId,
            state = snapshot.paper,
            saveStatus = snapshot.persistedSaveStatus(paperId),
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

@Suppress("MaxLineLength")
private fun MnemeUiSnapshot.persistedSaveStatus(paperId: String): EventRecordingStatus = savedPapers.saveStatus(paperId, engagement)

private const val EXTERNAL_EVENT_WRITE_ATTEMPTS = 3
private const val EXTERNAL_EVENT_RETRY_DELAY_MILLIS = 100L

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
            arxivUrl = paper.source.url,
        )
    externalActions.sharePaper(paper.paper.title, shareText)
    actions.sharePaper(paperId)
}
