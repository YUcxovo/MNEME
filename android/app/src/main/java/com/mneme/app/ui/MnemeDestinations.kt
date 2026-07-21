@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.runtime.Composable
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.LoadingState
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
    onRetry: () -> Unit,
    onAskQuestion: () -> Unit,
    onOpenSource: (String) -> Unit,
) {
    when (state) {
        PaperDetailUiState.Idle -> LoadingState(message = "Loading paper and summary...")
        is PaperDetailUiState.Loading -> LoadingState(message = state.message)
        is PaperDetailUiState.Content ->
            if (state.paper.paper.id == paperId) {
                PaperDetailScreen(
                    paper = state.paper,
                    onAskQuestion = onAskQuestion,
                    onOpenSource = onOpenSource,
                )
            } else {
                LoadingState(message = "Loading paper and summary...")
            }
        is PaperDetailUiState.Error -> ErrorState(message = state.message, onRetry = onRetry)
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
