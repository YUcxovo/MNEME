package com.mneme.app.ui

import com.mneme.app.data.behavior.BehavioralEventTracker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MnemeBehavioralEventRecorder(
    private val tracker: BehavioralEventTracker,
    private val scope: CoroutineScope,
) {
    private val _savedPaperIds = MutableStateFlow<Set<String>>(emptySet())
    val savedPaperIds: StateFlow<Set<String>> = _savedPaperIds.asStateFlow()

    fun recordPaperImpressions(paperIds: List<String>) {
        record { tracker.recordPaperImpressions(paperIds) }
    }

    fun recordPaperOpened(paperId: String) {
        record { tracker.recordPaperOpened(paperId) }
    }

    fun savePaper(paperId: String) {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        if (paperId in _savedPaperIds.value) {
            return
        }
        _savedPaperIds.value = _savedPaperIds.value + paperId
        record { tracker.recordPaperSaved(paperId) }
    }

    fun sharePaper(paperId: String) {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        record { tracker.recordPaperShared(paperId) }
    }

    fun recordQuestionAsked(paperId: String) {
        record { tracker.recordQuestionAsked(paperId) }
    }

    private fun record(block: suspend () -> Unit) {
        scope.launch {
            runCatching { block() }
        }
    }
}
