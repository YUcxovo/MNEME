package com.mneme.app.data.behavior

import com.mneme.app.data.local.BehavioralEventStore
import com.mneme.app.data.local.BehavioralEventType
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.network.BehavioralEventRemoteDataSource
import com.mneme.app.data.network.EventIngestionResultDto
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.UserEventDto
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.util.UUID

class BehavioralEventSyncCoordinatorTest {
    @Test
    fun syncPending_emptyQueueIsIdle() =
        runBlocking {
            val store = FakeStore(listOf(emptyList()))
            val coordinator = BehavioralEventSyncCoordinator(store, FakeRemote()) { SYNCED_AT }

            assertEquals(BehavioralEventSyncResult.Idle, coordinator.syncPending())
            assertTrue(store.syncedIds.isEmpty())
            assertTrue(store.returnedIds.isEmpty())
        }

    @Test
    fun syncPending_uploadsFrozenDtosAndMarksAcceptedAndDuplicateEventsSynced() =
        runBlocking {
            val store =
                FakeStore(
                    listOf(
                        listOf(
                            event(FIRST_EVENT_ID, "paper_opened", OCCURRED_AT, duration = 45_000),
                            event(SECOND_EVENT_ID, "question_asked", OCCURRED_AT + 60_000),
                        ),
                        emptyList(),
                    ),
                )
            val remote = FakeRemote(EventIngestionResultDto(accepted = 1, duplicates = 1))
            val coordinator = BehavioralEventSyncCoordinator(store, remote) { SYNCED_AT }

            val result = coordinator.syncPending()

            assertEquals(
                BehavioralEventSyncResult.Synced(processed = 2, accepted = 1, duplicates = 1),
                result,
            )
            assertEquals(listOf(FIRST_EVENT_ID, SECOND_EVENT_ID), store.syncedIds)
            assertEquals(SYNCED_AT, store.reservations.first().attemptedAt)
            assertEquals(
                SYNCED_AT - BehavioralEventSyncCoordinator.STALE_AFTER_MILLIS,
                store.reservations.first().staleBefore,
            )
            val payload = remote.requests.single()
            assertEquals("2026-07-24T03:00:00Z", payload.first().occurredAt)
            assertEquals(45_000L, payload.first().durationMillis)
            assertEquals("question_asked", payload.last().eventType)
        }

    @Test
    fun syncPending_networkFailureReturnsStableIdsToPending() =
        runBlocking {
            val store = FakeStore(listOf(listOf(event(FIRST_EVENT_ID, "paper_opened", OCCURRED_AT))))
            val remote = FakeRemote(failure = IOException("offline"))
            val coordinator = BehavioralEventSyncCoordinator(store, remote) { SYNCED_AT }

            val result = coordinator.syncPending()

            assertEquals(
                BehavioralEventSyncResult.Retry(BehavioralEventSyncCoordinator.NETWORK_ERROR),
                result,
            )
            assertEquals(listOf(FIRST_EVENT_ID), store.returnedIds)
            assertEquals(BehavioralEventSyncCoordinator.NETWORK_ERROR, store.returnedError)
            assertTrue(store.syncedIds.isEmpty())
        }

    @Test
    fun syncPending_serverFailureReturnsStableIdsForRetry() =
        runBlocking {
            val store = FakeStore(listOf(listOf(event(FIRST_EVENT_ID, "paper_opened", OCCURRED_AT))))
            val remote = FakeRemote(failure = apiFailure(503))
            val coordinator = BehavioralEventSyncCoordinator(store, remote) { SYNCED_AT }

            val result = coordinator.syncPending()

            assertEquals(BehavioralEventSyncResult.Retry("api_503"), result)
            assertEquals(listOf(FIRST_EVENT_ID), store.returnedIds)
            assertEquals("api_503", store.returnedError)
        }

    @Test
    fun syncPending_clientFailureStopsAutomaticRetryButPreservesPendingEvent() =
        runBlocking {
            val store = FakeStore(listOf(listOf(event(FIRST_EVENT_ID, "paper_opened", OCCURRED_AT))))
            val remote = FakeRemote(failure = apiFailure(401))
            val coordinator = BehavioralEventSyncCoordinator(store, remote) { SYNCED_AT }

            val result = coordinator.syncPending()

            assertEquals(BehavioralEventSyncResult.Failed("api_401"), result)
            assertEquals(listOf(FIRST_EVENT_ID), store.returnedIds)
            assertEquals("api_401", store.returnedError)
        }

    @Test
    fun syncPending_rejectsCountsThatDoNotCoverReservedBatch() =
        runBlocking {
            val store = FakeStore(listOf(listOf(event(FIRST_EVENT_ID, "paper_opened", OCCURRED_AT))))
            val remote = FakeRemote(EventIngestionResultDto(accepted = 0, duplicates = 0))
            val coordinator = BehavioralEventSyncCoordinator(store, remote) { SYNCED_AT }

            val result = coordinator.syncPending()

            assertEquals(
                BehavioralEventSyncResult.Retry(BehavioralEventSyncCoordinator.INVALID_RESULT),
                result,
            )
            assertEquals(listOf(FIRST_EVENT_ID), store.returnedIds)
            assertEquals(BehavioralEventSyncCoordinator.INVALID_RESULT, store.returnedError)
        }

    private data class Reservation(
        val limit: Int,
        val attemptedAt: Long,
        val staleBefore: Long,
    )

    private class FakeStore(
        batches: List<List<BehavioralEventEntity>>,
    ) : BehavioralEventStore {
        private val batches = ArrayDeque(batches)
        val reservations = mutableListOf<Reservation>()
        val syncedIds = mutableListOf<UUID>()
        val returnedIds = mutableListOf<UUID>()
        var returnedError: String? = null

        override suspend fun record(
            type: BehavioralEventType,
            paperId: UUID?,
            occurredAtEpochMillis: Long,
            durationMillis: Long?,
        ): UUID = error("record is not used by sync tests")

        override suspend fun recordOnce(
            eventId: UUID,
            type: BehavioralEventType,
            paperId: UUID?,
            occurredAtEpochMillis: Long,
            durationMillis: Long?,
        ): UUID = error("recordOnce is not used by sync tests")

        override suspend fun reservePendingBatch(
            limit: Int,
            attemptedAtEpochMillis: Long,
            staleBeforeEpochMillis: Long,
        ): List<BehavioralEventEntity> {
            reservations += Reservation(limit, attemptedAtEpochMillis, staleBeforeEpochMillis)
            return batches.removeFirstOrNull() ?: emptyList()
        }

        override suspend fun markBatchSynced(eventIds: List<UUID>) {
            syncedIds += eventIds
        }

        override suspend fun returnBatchToPending(
            eventIds: List<UUID>,
            error: String?,
        ) {
            returnedIds += eventIds
            returnedError = error
        }
    }

    private class FakeRemote(
        private val result: EventIngestionResultDto? = null,
        private val failure: IOException? = null,
    ) : BehavioralEventRemoteDataSource {
        val requests = mutableListOf<List<UserEventDto>>()

        override suspend fun uploadEvents(events: List<UserEventDto>): EventIngestionResultDto {
            requests += events
            failure?.let { throw it }
            return checkNotNull(result)
        }
    }

    companion object {
        private val FIRST_EVENT_ID = UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        private val SECOND_EVENT_ID = UUID.fromString("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        private const val PAPER_ID = "11111111-1111-4111-8111-111111111111"
        private const val OCCURRED_AT = 1_784_862_000_000L
        private const val SYNCED_AT = OCCURRED_AT + 120_000

        private fun apiFailure(statusCode: Int) =
            MnemeApiException(
                statusCode = statusCode,
                errorCode = "test_error",
                message = "Test API failure",
                requestId = "request-test",
            )

        private fun event(
            id: UUID,
            type: String,
            occurredAt: Long,
            duration: Long? = null,
        ) = BehavioralEventEntity(
            id = id.toString(),
            eventType = type,
            paperId = PAPER_ID,
            occurredAtEpochMillis = occurredAt,
            durationMillis = duration,
        )
    }
}
