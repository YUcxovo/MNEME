package com.mneme.app.data.behavior

import com.mneme.app.data.local.BehavioralEventStore
import com.mneme.app.data.local.BehavioralEventType
import com.mneme.app.data.local.entity.BehavioralEventEntity
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.UUID

class BehavioralEventTrackerTest {
    @Test
    fun existingInteractionsRecordContractEventsWithoutQuestionContent() =
        runBlocking {
            val store = RecordingStore()
            var scheduled = 0
            val tracker =
                QueuedBehavioralEventTracker(
                    store = store,
                    scheduleSync = { scheduled += 1 },
                    nowEpochMillis = { OCCURRED_AT },
                )

            tracker.recordPaperImpressions(listOf(FIRST_PAPER_ID.toString(), FIRST_PAPER_ID.toString()))
            tracker.recordPaperOpened(FIRST_PAPER_ID.toString())
            tracker.recordPaperSaved(FIRST_PAPER_ID.toString())
            tracker.recordPaperShared(FIRST_PAPER_ID.toString())
            tracker.recordQuestionAsked(FIRST_PAPER_ID.toString())

            assertEquals(
                listOf(
                    BehavioralEventType.PAPER_IMPRESSION,
                    BehavioralEventType.PAPER_OPENED,
                    BehavioralEventType.PAPER_SAVED,
                    BehavioralEventType.PAPER_SHARED,
                    BehavioralEventType.QUESTION_ASKED,
                ),
                store.recorded.map(RecordedEvent::type),
            )
            assertEquals(List(5) { FIRST_PAPER_ID }, store.recorded.map(RecordedEvent::paperId))
            assertEquals(List(5) { OCCURRED_AT }, store.recorded.map(RecordedEvent::occurredAt))
            assertEquals(5, scheduled)
        }

    @Test
    fun schedulerFailureDoesNotInvalidateTheDurableRoomBoundary() =
        runBlocking {
            val store = RecordingStore()
            val tracker =
                QueuedBehavioralEventTracker(
                    store = store,
                    scheduleSync = { error("WorkManager unavailable") },
                    nowEpochMillis = { OCCURRED_AT },
                )

            tracker.recordPaperSaved(FIRST_PAPER_ID.toString())

            assertEquals(1, store.recorded.size)
            assertEquals(BehavioralEventType.PAPER_SAVED, store.recorded.single().type)
        }

    @Test
    fun externalOpenForwardsStableIdentityToTheDurableStore() =
        runBlocking {
            val store = RecordingStore()
            val tracker =
                QueuedBehavioralEventTracker(
                    store = store,
                    scheduleSync = {},
                    nowEpochMillis = { OCCURRED_AT },
                )

            tracker.recordPaperOpenedOnce(EXTERNAL_EVENT_ID.toString(), FIRST_PAPER_ID.toString())

            assertEquals(listOf(EXTERNAL_EVENT_ID), store.recordedOnceIds)
            assertEquals(BehavioralEventType.PAPER_OPENED, store.recorded.single().type)
            assertEquals(FIRST_PAPER_ID, store.recorded.single().paperId)
        }

    private data class RecordedEvent(
        val type: BehavioralEventType,
        val paperId: UUID?,
        val occurredAt: Long,
        val duration: Long?,
    )

    private class RecordingStore : BehavioralEventStore {
        val recorded = mutableListOf<RecordedEvent>()
        val recordedOnceIds = mutableListOf<UUID>()

        override suspend fun record(
            type: BehavioralEventType,
            paperId: UUID?,
            occurredAtEpochMillis: Long,
            durationMillis: Long?,
        ): UUID {
            recorded += RecordedEvent(type, paperId, occurredAtEpochMillis, durationMillis)
            return UUID.randomUUID()
        }

        override suspend fun recordOnce(
            eventId: UUID,
            type: BehavioralEventType,
            paperId: UUID?,
            occurredAtEpochMillis: Long,
            durationMillis: Long?,
        ): UUID {
            recordedOnceIds += eventId
            record(type, paperId, occurredAtEpochMillis, durationMillis)
            return eventId
        }

        override suspend fun reservePendingBatch(
            limit: Int,
            attemptedAtEpochMillis: Long,
            staleBeforeEpochMillis: Long,
        ): List<BehavioralEventEntity> = emptyList()

        override suspend fun markBatchSynced(eventIds: List<UUID>) = Unit

        override suspend fun returnBatchToPending(
            eventIds: List<UUID>,
            error: String?,
        ) = Unit
    }

    companion object {
        private val FIRST_PAPER_ID = UUID.fromString("11111111-1111-4111-8111-111111111111")
        private val EXTERNAL_EVENT_ID = UUID.fromString("77777777-7777-4777-8777-777777777777")
        private const val OCCURRED_AT = 1_784_862_000_000L
    }
}
