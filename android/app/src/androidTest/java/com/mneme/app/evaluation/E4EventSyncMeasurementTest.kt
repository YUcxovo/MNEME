@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.behavior.BehavioralEventSyncCoordinator
import com.mneme.app.data.behavior.BehavioralEventSyncResult
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.BehavioralEventType
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.network.MnemeApiClient
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.ArrayDeque
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class E4EventSyncMeasurementTest {
    private lateinit var server: MockWebServer

    @Before
    fun startServer() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun stopServer() {
        server.shutdown()
    }

    @Test
    fun recordQueueFailureRetryAndDuplicateLatency() =
        runBlocking {
            E4MeasurementFiles.resetCsv(EVENT_FILE, EVENT_HEADER)
            var failures = 0
            repeat(WARMUP_ITERATIONS + MEASURED_ITERATIONS) { index ->
                val measured = index >= WARMUP_ITERATIONS
                val sample = runIteration(index)
                if (measured) {
                    val iteration = index - WARMUP_ITERATIONS + 1
                    sample.measurements.forEach { measurement ->
                        if (!measurement.success) {
                            failures += 1
                        }
                        record(iteration, measurement)
                    }
                }
            }
            assertEquals("Every measured event-sync stage must complete.", 0, failures)
        }

    private suspend fun runIteration(index: Int): EventIteration {
        val eventIds =
            listOf(
                UUID.nameUUIDFromBytes("e4-event-$index-impression".toByteArray()),
                UUID.nameUUIDFromBytes("e4-event-$index-open".toByteArray()),
                UUID.nameUUIDFromBytes("e4-event-$index-question".toByteArray()),
            )
        val paperId = UUID.nameUUIDFromBytes("e4-paper-$index".toByteArray())
        val firstDatabase = createDatabase()
        val firstStore =
            BehavioralEventRepository(
                behavioralEventDao = firstDatabase.behavioralEventDao(),
                idGenerator = ArrayDeque(eventIds)::removeFirst,
            )
        val measurements = mutableListOf<EventMeasurement>()
        try {
            val queueStartedAt = SystemClock.elapsedRealtimeNanos()
            recordThreeEvents(firstStore, paperId)
            val queued = firstStore.observeAll().first()
            measurements +=
                EventMeasurement(
                    scenario = "queue_write",
                    durationMillis = elapsedMillis(queueStartedAt),
                    success = queued.size == EVENT_COUNT,
                    outcome = if (queued.size == EVENT_COUNT) "pending" else "queue_mismatch",
                    finalState = queued.map { event -> event.syncState }.distinct().joinToString("+"),
                )

            server.enqueue(
                MockResponse()
                    .setResponseCode(503)
                    .setHeader("Content-Type", "application/json")
                    .setBody(
                        """{"code":"temporary","message":"controlled failure","request_id":"e4"}""",
                    ),
            )
            server.enqueue(successResponse(accepted = EVENT_COUNT, duplicates = 0))
            val remote =
                MnemeApiClient.create(
                    baseUrl = server.url("/v1/").toString(),
                    demoToken = "controlled-e4-token",
                )
            val coordinator =
                BehavioralEventSyncCoordinator(
                    store = firstStore,
                    remote = remote,
                    nowEpochMillis = { CONTROLLED_TIME + index },
                )

            val failureStartedAt = SystemClock.elapsedRealtimeNanos()
            val failure = coordinator.syncPending()
            val afterFailure = firstStore.observeAll().first()
            val retryable =
                failure is BehavioralEventSyncResult.Retry &&
                    afterFailure.all { event ->
                        event.syncState == BehavioralEventSyncState.PENDING.value
                    }
            measurements +=
                EventMeasurement(
                    scenario = "retryable_http_failure",
                    durationMillis = elapsedMillis(failureStartedAt),
                    success = retryable,
                    outcome = failure::class.java.simpleName,
                    finalState = afterFailure.map { event -> event.syncState }.distinct().joinToString("+"),
                )

            val retryStartedAt = SystemClock.elapsedRealtimeNanos()
            val retry = coordinator.syncPending()
            val afterRetry = firstStore.observeAll().first()
            val retrySuccess =
                retry ==
                    BehavioralEventSyncResult.Synced(
                        processed = EVENT_COUNT,
                        accepted = EVENT_COUNT,
                        duplicates = 0,
                    ) &&
                    afterRetry.all { event ->
                        event.syncState == BehavioralEventSyncState.SYNCED.value
                    }
            measurements +=
                EventMeasurement(
                    scenario = "retry_success",
                    durationMillis = elapsedMillis(retryStartedAt),
                    success = retrySuccess,
                    outcome = retry::class.java.simpleName,
                    accepted = (retry as? BehavioralEventSyncResult.Synced)?.accepted,
                    duplicates = (retry as? BehavioralEventSyncResult.Synced)?.duplicates,
                    finalState = afterRetry.map { event -> event.syncState }.distinct().joinToString("+"),
                )
        } finally {
            firstDatabase.close()
        }

        val duplicateDatabase = createDatabase()
        try {
            val duplicateStore =
                BehavioralEventRepository(
                    behavioralEventDao = duplicateDatabase.behavioralEventDao(),
                    idGenerator = ArrayDeque(eventIds)::removeFirst,
                )
            recordThreeEvents(duplicateStore, paperId)
            server.enqueue(successResponse(accepted = 0, duplicates = EVENT_COUNT))
            val duplicateCoordinator =
                BehavioralEventSyncCoordinator(
                    store = duplicateStore,
                    remote =
                        MnemeApiClient.create(
                            baseUrl = server.url("/v1/").toString(),
                            demoToken = "controlled-e4-token",
                        ),
                    nowEpochMillis = { CONTROLLED_TIME + index + 1_000 },
                )
            val duplicateStartedAt = SystemClock.elapsedRealtimeNanos()
            val duplicate = duplicateCoordinator.syncPending()
            val afterDuplicate = duplicateStore.observeAll().first()
            val duplicateSuccess =
                duplicate ==
                    BehavioralEventSyncResult.Synced(
                        processed = EVENT_COUNT,
                        accepted = 0,
                        duplicates = EVENT_COUNT,
                    ) &&
                    afterDuplicate.all { event ->
                        event.syncState == BehavioralEventSyncState.SYNCED.value
                    }
            measurements +=
                EventMeasurement(
                    scenario = "duplicate_replay",
                    durationMillis = elapsedMillis(duplicateStartedAt),
                    success = duplicateSuccess,
                    outcome = duplicate::class.java.simpleName,
                    accepted = (duplicate as? BehavioralEventSyncResult.Synced)?.accepted,
                    duplicates = (duplicate as? BehavioralEventSyncResult.Synced)?.duplicates,
                    finalState = afterDuplicate.map { event -> event.syncState }.distinct().joinToString("+"),
                )
        } finally {
            duplicateDatabase.close()
        }
        return EventIteration(measurements)
    }

    private suspend fun recordThreeEvents(
        store: BehavioralEventRepository,
        paperId: UUID,
    ) {
        store.record(
            type = BehavioralEventType.PAPER_IMPRESSION,
            paperId = paperId,
            occurredAtEpochMillis = CONTROLLED_TIME,
        )
        store.record(
            type = BehavioralEventType.PAPER_OPENED,
            paperId = paperId,
            occurredAtEpochMillis = CONTROLLED_TIME + 1,
            durationMillis = 1_500,
        )
        store.record(
            type = BehavioralEventType.QUESTION_ASKED,
            paperId = paperId,
            occurredAtEpochMillis = CONTROLLED_TIME + 2,
        )
    }

    private fun createDatabase(): MnemeDatabase {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Room
            .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    private fun successResponse(
        accepted: Int,
        duplicates: Int,
    ): MockResponse =
        MockResponse()
            .setResponseCode(200)
            .setHeader("Content-Type", "application/json")
            .setBody("""{"accepted":$accepted,"duplicates":$duplicates}""")

    private fun record(
        iteration: Int,
        measurement: EventMeasurement,
    ) {
        E4MeasurementFiles.appendCsv(
            EVENT_FILE,
            listOf(
                "event_sync",
                measurement.scenario,
                iteration,
                EVENT_COUNT,
                measurement.durationMillis,
                measurement.success,
                measurement.outcome,
                measurement.accepted,
                measurement.duplicates,
                measurement.finalState,
            ),
        )
    }

    private fun elapsedMillis(startedAtNanos: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAtNanos) / NANOS_PER_MILLISECOND

    private data class EventIteration(
        val measurements: List<EventMeasurement>,
    )

    private data class EventMeasurement(
        val scenario: String,
        val durationMillis: Double,
        val success: Boolean,
        val outcome: String,
        val accepted: Int? = null,
        val duplicates: Int? = null,
        val finalState: String,
    )

    private companion object {
        const val EVENT_FILE = "event_sync_measurements.csv"
        const val EVENT_COUNT = 3
        const val WARMUP_ITERATIONS = 3
        const val MEASURED_ITERATIONS = 30
        const val CONTROLLED_TIME = 1_780_000_000_000L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        val EVENT_HEADER =
            listOf(
                "track",
                "scenario",
                "iteration",
                "event_count",
                "duration_ms",
                "success",
                "outcome",
                "accepted",
                "duplicates",
                "final_state",
            )
    }
}
