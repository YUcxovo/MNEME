@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.runtime.Composable
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.LoadingState
import com.mneme.app.ui.graph.GraphScreen
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.interests.InterestsScreen
import com.mneme.app.ui.paper.PaperDetailScreen
import com.mneme.app.ui.qa.QaScreen

@Composable
internal fun InterestsDestination(
    homeState: HomeUiState,
    onRetry: () -> Unit,
) {
    when (homeState) {
        HomeUiState.Loading -> LoadingState(message = "Loading research interests...")
        HomeUiState.Empty ->
            ErrorState(
                message = "No research interests are available.",
                onRetry = onRetry,
            )
        is HomeUiState.Error -> ErrorState(message = homeState.message, onRetry = onRetry)
        is HomeUiState.Content ->
            InterestsScreen(
                interests = homeState.briefing.interests,
                disclosure = homeState.briefing.disclosure,
            )
    }
}

@Composable
internal fun PaperDestination(
    paperId: String,
    state: PaperDetailUiState,
    actions: PaperDestinationActions,
) {
    when (state) {
        PaperDetailUiState.Idle -> LoadingState(message = "Loading paper and summary...")
        is PaperDetailUiState.Loading -> LoadingState(message = state.message)
        is PaperDetailUiState.Content ->
            if (state.paper.paper.id == paperId) {
                PaperDetailScreen(
                    paper = state.paper,
                    onAskQuestion = actions.askQuestion,
                    onExploreGraph = actions.exploreGraph,
                    onOpenSource = actions.openSource,
                )
            } else {
                LoadingState(message = "Loading paper and summary...")
            }
        is PaperDetailUiState.Error -> ErrorState(message = state.message, onRetry = actions.retry)
    }
}

internal data class PaperDestinationActions(
    val retry: () -> Unit,
    val askQuestion: () -> Unit,
    val exploreGraph: () -> Unit,
    val openSource: (String) -> Unit,
)

@Composable
internal fun GraphDestination(
    paperId: String,
    state: GraphUiState,
    onRetry: () -> Unit,
    onOpenPaper: (String) -> Unit,
) {
    when (state) {
        GraphUiState.Idle -> LoadingState(message = "Loading citation connections...")
        is GraphUiState.Loading -> LoadingState(message = "Loading citation connections...")
        is GraphUiState.Content ->
            if (state.graph.centerId == paperId) {
                GraphScreen(
                    graph = state.graph,
                    onRetry = onRetry,
                    onOpenPaper = onOpenPaper,
                )
            } else {
                LoadingState(message = "Loading citation connections...")
            }
        is GraphUiState.Error ->
            if (state.paperId == paperId) {
                ErrorState(message = state.message, onRetry = onRetry)
            } else {
                LoadingState(message = "Loading citation connections...")
            }
    }
}

@Composable
internal fun QaDestination(
    paperId: String,
    state: QaUiState,
    onSubmit: (String) -> Unit,
    onOpenSource: (String) -> Unit,
) {
    val scopedState =
        when (state) {
            QaUiState.Idle -> QaUiState.Idle
            is QaUiState.Loading -> state.takeIf { it.paperId == paperId } ?: QaUiState.Idle
            is QaUiState.Content -> state.takeIf { it.qa.paperId == paperId } ?: QaUiState.Idle
            is QaUiState.Error -> state.takeIf { it.paperId == paperId } ?: QaUiState.Idle
        }
    QaScreen(
        paperId = paperId,
        state = scopedState,
        onSubmit = onSubmit,
        onOpenSource = onOpenSource,
    )
}
