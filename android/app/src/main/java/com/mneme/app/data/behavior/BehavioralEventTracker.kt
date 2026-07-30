package com.mneme.app.data.behavior

import com.mneme.app.data.local.BehavioralEventStore
import com.mneme.app.data.local.BehavioralEventType
import java.util.UUID

interface BehavioralEventTracker {
    suspend fun recordPaperImpressions(paperIds: List<String>)

    suspend fun recordPaperOpened(paperId: String)

    suspend fun recordPaperSaved(paperId: String)

    suspend fun recordPaperShared(paperId: String)

    suspend fun recordQuestionAsked(paperId: String)
}

object NoOpBehavioralEventTracker : BehavioralEventTracker {
    override suspend fun recordPaperImpressions(paperIds: List<String>) = Unit

    override suspend fun recordPaperOpened(paperId: String) = Unit

    override suspend fun recordPaperSaved(paperId: String) = Unit

    override suspend fun recordPaperShared(paperId: String) = Unit

    override suspend fun recordQuestionAsked(paperId: String) = Unit
}

class QueuedBehavioralEventTracker(
    private val store: BehavioralEventStore,
    private val scheduleSync: () -> Unit,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) : BehavioralEventTracker {
    override suspend fun recordPaperImpressions(paperIds: List<String>) {
        val distinctPaperIds = paperIds.distinct().map(UUID::fromString)
        if (distinctPaperIds.isEmpty()) return

        val occurredAt = nowEpochMillis()
        distinctPaperIds.forEach { paperId ->
            store.record(
                type = BehavioralEventType.PAPER_IMPRESSION,
                paperId = paperId,
                occurredAtEpochMillis = occurredAt,
            )
        }
        scheduleSync()
    }

    override suspend fun recordPaperOpened(paperId: String) {
        recordPaperEvent(BehavioralEventType.PAPER_OPENED, paperId)
    }

    override suspend fun recordPaperSaved(paperId: String) {
        recordPaperEvent(BehavioralEventType.PAPER_SAVED, paperId)
    }

    override suspend fun recordPaperShared(paperId: String) {
        recordPaperEvent(BehavioralEventType.PAPER_SHARED, paperId)
    }

    override suspend fun recordQuestionAsked(paperId: String) {
        recordPaperEvent(BehavioralEventType.QUESTION_ASKED, paperId)
    }

    private suspend fun recordPaperEvent(
        type: BehavioralEventType,
        paperId: String,
    ) {
        store.record(
            type = type,
            paperId = UUID.fromString(paperId),
            occurredAtEpochMillis = nowEpochMillis(),
        )
        scheduleSync()
    }
}
