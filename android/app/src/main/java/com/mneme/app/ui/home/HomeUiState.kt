package com.mneme.app.ui.home

import com.mneme.app.ui.model.BriefingUiModel

sealed interface HomeUiState {
    data object Loading : HomeUiState

    data object Empty : HomeUiState

    data class Error(
        val message: String,
    ) : HomeUiState

    data class Content(
        val briefing: BriefingUiModel,
    ) : HomeUiState
}
