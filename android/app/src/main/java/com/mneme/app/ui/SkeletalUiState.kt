package com.mneme.app.ui

import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.QaUiModel

sealed interface OnboardingUiState {
    data object Checking : OnboardingUiState

    data object Ready : OnboardingUiState

    data object AwaitingSeed : OnboardingUiState

    data class Loading(
        val arxivReference: String,
    ) : OnboardingUiState

    data class Error(
        val arxivReference: String,
        val message: String,
    ) : OnboardingUiState
}

sealed interface PaperDetailUiState {
    data object Idle : PaperDetailUiState

    data class Loading(
        val paperId: String,
        val message: String,
    ) : PaperDetailUiState

    data class Content(
        val paper: PaperDetailUiModel,
    ) : PaperDetailUiState

    data class Error(
        val paperId: String,
        val message: String,
    ) : PaperDetailUiState
}

sealed interface QaUiState {
    data object Idle : QaUiState

    data class Loading(
        val paperId: String,
        val question: String,
        val exchanges: List<QaUiModel>,
    ) : QaUiState

    data class Content(
        val paperId: String,
        val exchanges: List<QaUiModel>,
    ) : QaUiState

    data class Error(
        val paperId: String,
        val question: String,
        val message: String,
        val exchanges: List<QaUiModel>,
    ) : QaUiState
}

sealed interface GraphUiState {
    data object Idle : GraphUiState

    data class Loading(
        val paperId: String,
    ) : GraphUiState

    data class Content(
        val graph: GraphUiModel,
    ) : GraphUiState

    data class Error(
        val paperId: String,
        val message: String,
    ) : GraphUiState
}

sealed interface InterestEditUiState {
    data object Idle : InterestEditUiState

    data object Saving : InterestEditUiState

    data object Saved : InterestEditUiState

    data class Error(
        val message: String,
    ) : InterestEditUiState
}

sealed interface SavedPapersUiState {
    data object Loading : SavedPapersUiState

    data class Content(
        val papers: List<PaperUiModel>,
    ) : SavedPapersUiState

    data class Error(
        val message: String,
    ) : SavedPapersUiState
}

internal fun QaUiState.paperIdOrNull(): String? =
    when (this) {
        QaUiState.Idle -> null
        is QaUiState.Loading -> paperId
        is QaUiState.Content -> paperId
        is QaUiState.Error -> paperId
    }

internal fun QaUiState.completedExchanges(): List<QaUiModel> =
    when (this) {
        QaUiState.Idle -> emptyList()
        is QaUiState.Loading -> exchanges
        is QaUiState.Content -> exchanges
        is QaUiState.Error -> exchanges
    }
