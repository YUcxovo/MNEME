package com.mneme.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
internal fun MnemeViewModel.collectUiSnapshot(): MnemeUiSnapshot {
    val home by homeState.collectAsStateWithLifecycle()
    val paper by paperState.collectAsStateWithLifecycle()
    val qa by qaState.collectAsStateWithLifecycle()
    val graph by graphState.collectAsStateWithLifecycle()
    val interestEdit by interestEditState.collectAsStateWithLifecycle()
    val engagement by behavioralEvents.engagementState.collectAsStateWithLifecycle()
    return MnemeUiSnapshot(home, paper, qa, graph, interestEdit, engagement)
}
