package com.mneme.app.ui

import androidx.activity.compose.ReportDrawnWhen
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.mneme.app.ui.home.HomeUiState

@Composable
internal fun MnemeViewModel.collectUiSnapshot(onboardingState: OnboardingUiState): MnemeUiSnapshot {
    val home by homeState.collectAsStateWithLifecycle()
    val paper by paperState.collectAsStateWithLifecycle()
    val qa by qaState.collectAsStateWithLifecycle()
    val graph by graphState.collectAsStateWithLifecycle()
    val interestEdit by interestEditState.collectAsStateWithLifecycle()
    val engagement by behavioralEvents.engagementState.collectAsStateWithLifecycle()
    ReportDrawnWhen {
        when (onboardingState) {
            OnboardingUiState.AwaitingSeed -> true
            is OnboardingUiState.Error -> true
            OnboardingUiState.Ready -> home is HomeUiState.Content || home is HomeUiState.Error
            OnboardingUiState.Checking -> false
            is OnboardingUiState.Loading -> false
        }
    }
    return MnemeUiSnapshot(home, paper, qa, graph, interestEdit, engagement)
}
