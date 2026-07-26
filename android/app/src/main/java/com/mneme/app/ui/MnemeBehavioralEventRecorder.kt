package com.mneme.app.ui

import com.mneme.app.data.behavior.BehavioralEventTracker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

class MnemeBehavioralEventRecorder(
    private val tracker: BehavioralEventTracker,
    private val scope: CoroutineScope,
) {
    fun recordPaperImpressions(paperIds: List<String>) {
        record { tracker.recordPaperImpressions(paperIds) }
    }

    fun recordPaperOpened(paperId: String) {
        record { tracker.recordPaperOpened(paperId) }
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
