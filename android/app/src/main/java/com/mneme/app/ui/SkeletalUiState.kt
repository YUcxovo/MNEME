package com.mneme.app.ui

import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
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
    ) : QaUiState

    data class Content(
        val qa: QaUiModel,
    ) : QaUiState

    data class Error(
        val paperId: String,
        val question: String,
        val message: String,
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

internal fun QaUiState.submittedQuestion(): String? =
    when (this) {
        QaUiState.Idle -> null
        is QaUiState.Loading -> question
        is QaUiState.Content -> qa.question
        is QaUiState.Error -> question
    }
