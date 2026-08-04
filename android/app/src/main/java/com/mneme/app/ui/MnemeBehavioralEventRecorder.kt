package com.mneme.app.ui

import com.mneme.app.data.behavior.BehavioralEventTracker
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class EventRecordingStatus {
    IDLE,
    RECORDING,
    RECORDED,
    FAILED,
}

data class PaperEngagementUiState(
    val saveStatuses: Map<String, EventRecordingStatus> = emptyMap(),
    val shareStatuses: Map<String, EventRecordingStatus> = emptyMap(),
) {
    fun saveStatus(paperId: String): EventRecordingStatus = saveStatuses[paperId] ?: EventRecordingStatus.IDLE

    fun shareStatus(paperId: String): EventRecordingStatus = shareStatuses[paperId] ?: EventRecordingStatus.IDLE
}

class MnemeBehavioralEventRecorder(
    private val tracker: BehavioralEventTracker,
    private val scope: CoroutineScope,
) {
    private val _engagementState = MutableStateFlow(PaperEngagementUiState())
    val engagementState: StateFlow<PaperEngagementUiState> = _engagementState.asStateFlow()

    fun recordPaperImpressions(paperIds: List<String>) {
        record { tracker.recordPaperImpressions(paperIds) }
    }

    fun recordPaperOpened(paperId: String) {
        record { tracker.recordPaperOpened(paperId) }
    }

    suspend fun recordPaperOpenedOnce(
        eventId: String,
        paperId: String,
    ): Boolean {
        if (!tracker.recordsDurably) return false
        tracker.recordPaperOpenedOnce(eventId, paperId)
        return true
    }

    fun savePaper(paperId: String) {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        if (
            _engagementState.value.saveStatus(paperId) in
            setOf(EventRecordingStatus.RECORDING, EventRecordingStatus.RECORDED)
        ) {
            return
        }
        if (!tracker.recordsDurably) {
            updateSaveStatus(paperId, EventRecordingStatus.FAILED)
            return
        }
        updateSaveStatus(paperId, EventRecordingStatus.RECORDING)
        recordEngagement(
            paperId = paperId,
            currentStatus = { _engagementState.value.saveStatus(it) },
            updateStatus = ::updateSaveStatus,
        ) {
            tracker.recordPaperSaved(paperId)
        }
    }

    fun sharePaper(paperId: String) {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        if (_engagementState.value.shareStatus(paperId) == EventRecordingStatus.RECORDING) {
            return
        }
        if (!tracker.recordsDurably) {
            updateShareStatus(paperId, EventRecordingStatus.FAILED)
            return
        }
        updateShareStatus(paperId, EventRecordingStatus.RECORDING)
        recordEngagement(
            paperId = paperId,
            currentStatus = { _engagementState.value.shareStatus(it) },
            updateStatus = ::updateShareStatus,
        ) {
            tracker.recordPaperShared(paperId)
        }
    }

    fun recordQuestionAsked(paperId: String) {
        record { tracker.recordQuestionAsked(paperId) }
    }

    private fun record(block: suspend () -> Unit) {
        scope.launch {
            runCatching { block() }
        }
    }

    private fun recordEngagement(
        paperId: String,
        currentStatus: (String) -> EventRecordingStatus,
        updateStatus: (String, EventRecordingStatus) -> Unit,
        block: suspend () -> Unit,
    ) {
        val recordingJob =
            scope.launch {
                try {
                    block()
                    updateStatus(paperId, EventRecordingStatus.RECORDED)
                } catch (error: CancellationException) {
                    updateStatus(paperId, EventRecordingStatus.FAILED)
                    throw error
                } catch (_: Exception) {
                    updateStatus(paperId, EventRecordingStatus.FAILED)
                }
            }
        recordingJob.invokeOnCompletion { cause ->
            if (
                cause is CancellationException &&
                currentStatus(paperId) == EventRecordingStatus.RECORDING
            ) {
                updateStatus(paperId, EventRecordingStatus.FAILED)
            }
        }
    }

    private fun updateSaveStatus(
        paperId: String,
        status: EventRecordingStatus,
    ) {
        _engagementState.update { state ->
            state.copy(saveStatuses = state.saveStatuses + (paperId to status))
        }
    }

    private fun updateShareStatus(
        paperId: String,
        status: EventRecordingStatus,
    ) {
        _engagementState.update { state ->
            state.copy(shareStatuses = state.shareStatuses + (paperId to status))
        }
    }
}
