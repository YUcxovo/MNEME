@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.BuildConfig
import com.mneme.app.data.behavior.BehavioralEventSyncCoordinator
import com.mneme.app.data.behavior.BehavioralEventSyncResult
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.BehavioralEventType
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.network.BehavioralEventRemoteDataSource
import com.mneme.app.data.network.MnemeApiClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import java.util.ArrayDeque
import java.util.UUID
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class E4LiveBackendClosedLoopTest {
    @Test
    fun recordDurableQueueThroughHttpFailureAndLiveIdempotentReplay() =
        runBlocking {
            val arguments = InstrumentationRegistry.getArguments()
            val baseUrl = arguments.getString(BASE_URL_ARGUMENT)
            val token = arguments.getString(TOKEN_ARGUMENT)
            E4MeasurementFiles.resetCsv(FORMAL_FILE, FORMAL_HEADER)
            require(!baseUrl.isNullOrBlank() && !token.isNullOrBlank()) {
                "Live E4 evaluation requires explicit backend URL and token arguments."
            }
            check(BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
                "Formal event-sync measurement requires a blank build-time token so that " +
                    "background synchronization cannot share the production Room database."
            }

            val iterations = resolveIterations(arguments.getString(ITERATIONS_ARGUMENT))
            val context = ApplicationProvider.getApplicationContext<Context>()
            val liveRemote = MnemeApiClient.create(requireNotNull(baseUrl), requireNotNull(token))
            val paperId =
                arguments
                    .getString(PAPER_ID_ARGUMENT)
                    ?.takeIf(String::isNotBlank)
                    ?.let(UUID::fromString)
                    ?: liveRemote
                        .listPapers(limit = 1)
                        .items
                        .firstOrNull()
                        ?.id
                        ?.let(UUID::fromString)
                    ?: error("The live backend needs at least one paper for the event-sync trace.")
            liveRemote.getHealth()

            var failures = 0
            try {
                repeat(iterations) { index ->
                    failures +=
                        runBatch(
                            context = context,
                            liveRemote = liveRemote,
                            paperId = paperId,
                            iteration = index + 1,
                        )
                }
            } finally {
                closeProductionDatabase(context)
            }

            assertEquals("Every formal event-sync stage must complete.", 0, failures)
        }

    private suspend fun runBatch(
        context: Context,
        liveRemote: BehavioralEventRemoteDataSource,
        paperId: UUID,
        iteration: Int,
    ): Int {
        val eventIds = List(EVENT_COUNT) { UUID.randomUUID() }
        val occurredAt = System.currentTimeMillis() - EVENT_CLOCK_MARGIN_MILLIS
        var failures = 0
        var primaryDatabase: MnemeDatabase? = null
        var primaryStore: BehavioralEventRepository? = null
        var reopenedReady = false
        var recoveredFromHttpFailure = false
        var liveUploadAccepted = false

        failures +=
            captureStage(
                scenario = "file_room_queue_write",
                iteration = iteration,
                eventIds = eventIds,
            ) {
                check(closeProductionDatabase(context)) {
                    "The production Room database could not be cleared before the batch."
                }
                primaryDatabase =
                    MnemeDatabase.create(context).also { database ->
                        database.openHelper.writableDatabase
                    }
                primaryStore =
                    BehavioralEventRepository(
                        behavioralEventDao = requireNotNull(primaryDatabase).behavioralEventDao(),
                        idGenerator = ArrayDeque(eventIds)::removeFirst,
                    )
                val startedAt = SystemClock.elapsedRealtimeNanos()
                recordThreeEvents(requireNotNull(primaryStore), paperId, occurredAt)
                val durationMillis = elapsedMillis(startedAt)
                val queued = requireNotNull(primaryStore).observeAll().first()
                StageObservation(
                    durationMillis = durationMillis,
                    success =
                        queued.matches(
                            eventIds = eventIds,
                            expectedState = BehavioralEventSyncState.PENDING,
                            expectedAttemptCount = 0,
                        ),
                    outcome = "three_events_written",
                    finalState = queued.stateSummary(),
                )
            }

        val databaseAfterQueue = primaryDatabase
        val closedAfterQueue =
            databaseAfterQueue != null &&
                runCatching {
                    databaseAfterQueue.close()
                }.isSuccess
        primaryDatabase = null
        primaryStore = null
        failures +=
            if (closedAfterQueue) {
                captureStage(
                    scenario = "file_room_reopen_pending",
                    iteration = iteration,
                    eventIds = eventIds,
                ) {
                    val startedAt = SystemClock.elapsedRealtimeNanos()
                    primaryDatabase = MnemeDatabase.create(context)
                    primaryStore =
                        BehavioralEventRepository(
                            behavioralEventDao = requireNotNull(primaryDatabase).behavioralEventDao(),
                        )
                    val restored = requireNotNull(primaryStore).observeAll().first()
                    val durationMillis = elapsedMillis(startedAt)
                    reopenedReady =
                        restored.matches(
                            eventIds = eventIds,
                            expectedState = BehavioralEventSyncState.PENDING,
                            expectedAttemptCount = 0,
                        )
                    StageObservation(
                        durationMillis = durationMillis,
                        success = reopenedReady,
                        outcome = "pending_events_restored",
                        finalState = restored.stateSummary(),
                    )
                }
            } else {
                recordSkippedStage(
                    scenario = "file_room_reopen_pending",
                    iteration = iteration,
                    eventIds = eventIds,
                    reason = "queue_database_close_failed",
                )
            }

        val mockServer =
            if (reopenedReady && primaryStore != null) {
                runCatching { MockWebServer().also(MockWebServer::start) }.getOrNull()
            } else {
                null
            }
        failures +=
            when {
                !reopenedReady || primaryStore == null ->
                    recordSkippedStage(
                        scenario = "http_503_pending_recovery",
                        iteration = iteration,
                        eventIds = eventIds,
                        reason = "reopened_store_unavailable",
                    )
                mockServer == null ->
                    recordSkippedStage(
                        scenario = "http_503_pending_recovery",
                        iteration = iteration,
                        eventIds = eventIds,
                        reason = "mock_http_server_unavailable",
                    )
                else ->
                    try {
                        captureStage(
                            scenario = "http_503_pending_recovery",
                            iteration = iteration,
                            eventIds = eventIds,
                        ) {
                            mockServer.enqueue(temporaryFailureResponse())
                            val controlledRemote =
                                MnemeApiClient.create(
                                    baseUrl = mockServer.url("/v1/").toString(),
                                    demoToken = CONTROLLED_TOKEN,
                                )
                            val coordinator =
                                BehavioralEventSyncCoordinator(
                                    store = requireNotNull(primaryStore),
                                    remote = controlledRemote,
                                )
                            val startedAt = SystemClock.elapsedRealtimeNanos()
                            val result = coordinator.syncPending()
                            val durationMillis = elapsedMillis(startedAt)
                            val afterFailure = requireNotNull(primaryStore).observeAll().first()
                            val request =
                                mockServer.takeRequest(
                                    MOCK_REQUEST_TIMEOUT_SECONDS,
                                    TimeUnit.SECONDS,
                                )
                            recoveredFromHttpFailure =
                                result ==
                                BehavioralEventSyncResult.Retry(
                                    API_503,
                                ) &&
                                afterFailure.matches(
                                    eventIds = eventIds,
                                    expectedState = BehavioralEventSyncState.PENDING,
                                    expectedAttemptCount = 1,
                                    expectedError = API_503,
                                ) &&
                                request.matchesEventUpload(eventIds)
                            StageObservation(
                                durationMillis = durationMillis,
                                success = recoveredFromHttpFailure,
                                outcome = result.describe(),
                                finalState = afterFailure.stateSummary(),
                            )
                        }
                    } finally {
                        runCatching(mockServer::shutdown)
                    }
            }

        failures +=
            if (recoveredFromHttpFailure && primaryStore != null) {
                val store = requireNotNull(primaryStore)
                captureStage(
                    scenario = "live_backend_upload",
                    iteration = iteration,
                    eventIds = eventIds,
                ) {
                    val coordinator =
                        BehavioralEventSyncCoordinator(
                            store = store,
                            remote = liveRemote,
                        )
                    val startedAt = SystemClock.elapsedRealtimeNanos()
                    val result = coordinator.syncPending()
                    val durationMillis = elapsedMillis(startedAt)
                    val afterUpload = store.observeAll().first()
                    val synced = result as? BehavioralEventSyncResult.Synced
                    liveUploadAccepted =
                        synced ==
                        BehavioralEventSyncResult.Synced(
                            processed = EVENT_COUNT,
                            accepted = EVENT_COUNT,
                            duplicates = 0,
                        ) &&
                        afterUpload.matches(
                            eventIds = eventIds,
                            expectedState = BehavioralEventSyncState.SYNCED,
                            expectedAttemptCount = 2,
                        )
                    StageObservation(
                        durationMillis = durationMillis,
                        success = liveUploadAccepted,
                        outcome = result.describe(),
                        accepted = synced?.accepted,
                        duplicates = synced?.duplicates,
                        finalState = afterUpload.stateSummary(),
                    )
                }
            } else {
                recordSkippedStage(
                    scenario = "live_backend_upload",
                    iteration = iteration,
                    eventIds = eventIds,
                    reason = "http_503_recovery_not_verified",
                )
            }

        runCatching { primaryDatabase?.close() }
        primaryDatabase = null
        primaryStore = null

        var replayDatabase: MnemeDatabase? = null
        failures +=
            if (liveUploadAccepted) {
                try {
                    captureStage(
                        scenario = "live_backend_duplicate_replay",
                        iteration = iteration,
                        eventIds = eventIds,
                    ) {
                        check(closeProductionDatabase(context)) {
                            "The production Room database could not be cleared before replay."
                        }
                        replayDatabase =
                            MnemeDatabase.create(context).also { database ->
                                database.openHelper.writableDatabase
                            }
                        val replayStore =
                            BehavioralEventRepository(
                                behavioralEventDao =
                                    requireNotNull(replayDatabase).behavioralEventDao(),
                                idGenerator = ArrayDeque(eventIds)::removeFirst,
                            )
                        recordThreeEvents(replayStore, paperId, occurredAt)
                        val coordinator =
                            BehavioralEventSyncCoordinator(
                                store = replayStore,
                                remote = liveRemote,
                            )
                        val startedAt = SystemClock.elapsedRealtimeNanos()
                        val result = coordinator.syncPending()
                        val durationMillis = elapsedMillis(startedAt)
                        val afterReplay = replayStore.observeAll().first()
                        val synced = result as? BehavioralEventSyncResult.Synced
                        StageObservation(
                            durationMillis = durationMillis,
                            success =
                                synced ==
                                    BehavioralEventSyncResult.Synced(
                                        processed = EVENT_COUNT,
                                        accepted = 0,
                                        duplicates = EVENT_COUNT,
                                    ) &&
                                    afterReplay.matches(
                                        eventIds = eventIds,
                                        expectedState = BehavioralEventSyncState.SYNCED,
                                        expectedAttemptCount = 1,
                                    ),
                            outcome = result.describe(),
                            accepted = synced?.accepted,
                            duplicates = synced?.duplicates,
                            finalState = afterReplay.stateSummary(),
                        )
                    }
                } finally {
                    runCatching { replayDatabase?.close() }
                    closeProductionDatabase(context)
                }
            } else {
                recordSkippedStage(
                    scenario = "live_backend_duplicate_replay",
                    iteration = iteration,
                    eventIds = eventIds,
                    reason = "live_upload_not_accepted",
                )
            }
        return failures
    }

    private suspend fun captureStage(
        scenario: String,
        iteration: Int,
        eventIds: List<UUID>,
        operation: suspend () -> StageObservation,
    ): Int {
        val stageStartedAt = SystemClock.elapsedRealtimeNanos()
        val observation =
            try {
                operation()
            } catch (error: CancellationException) {
                record(
                    scenario = scenario,
                    iteration = iteration,
                    eventIds = eventIds,
                    durationMillis = elapsedMillis(stageStartedAt),
                    success = false,
                    outcome = "cancelled",
                    finalState = "unknown",
                )
                throw error
            } catch (error: Exception) {
                StageObservation(
                    durationMillis = elapsedMillis(stageStartedAt),
                    success = false,
                    outcome = "exception_${error::class.java.simpleName}",
                    finalState = "unknown",
                )
            }
        return record(
            scenario = scenario,
            iteration = iteration,
            eventIds = eventIds,
            durationMillis = observation.durationMillis,
            success = observation.success,
            outcome = observation.outcome,
            accepted = observation.accepted,
            duplicates = observation.duplicates,
            finalState = observation.finalState,
        )
    }

    private fun recordSkippedStage(
        scenario: String,
        iteration: Int,
        eventIds: List<UUID>,
        reason: String,
    ): Int =
        record(
            scenario = scenario,
            iteration = iteration,
            eventIds = eventIds,
            durationMillis = 0.0,
            success = false,
            outcome = "skipped_$reason",
            finalState = "unknown",
        )

    private suspend fun recordThreeEvents(
        store: BehavioralEventRepository,
        paperId: UUID,
        occurredAt: Long,
    ) {
        store.record(
            type = BehavioralEventType.PAPER_IMPRESSION,
            paperId = paperId,
            occurredAtEpochMillis = occurredAt,
        )
        store.record(
            type = BehavioralEventType.PAPER_OPENED,
            paperId = paperId,
            occurredAtEpochMillis = occurredAt + 1,
            durationMillis = 1_500,
        )
        store.record(
            type = BehavioralEventType.QUESTION_ASKED,
            paperId = paperId,
            occurredAtEpochMillis = occurredAt + 2,
        )
    }

    private fun record(
        scenario: String,
        iteration: Int,
        eventIds: List<UUID>,
        durationMillis: Double,
        success: Boolean,
        outcome: String,
        accepted: Int? = null,
        duplicates: Int? = null,
        finalState: String,
    ): Int {
        E4MeasurementFiles.appendCsv(
            FORMAL_FILE,
            listOf(
                "event_sync_formal",
                scenario,
                iteration,
                EVENT_COUNT,
                durationMillis,
                success,
                outcome,
                accepted,
                duplicates,
                finalState,
                eventIds.joinToString("+"),
            ),
        )
        return if (success) 0 else 1
    }

    private fun closeProductionDatabase(context: Context): Boolean {
        context.deleteDatabase(MnemeDatabase.DATABASE_NAME)
        val databasePath = context.getDatabasePath(MnemeDatabase.DATABASE_NAME)
        val walPath = databasePath.parentFile?.resolve("${databasePath.name}-wal")
        val sharedMemoryPath = databasePath.parentFile?.resolve("${databasePath.name}-shm")
        val journalPath = databasePath.parentFile?.resolve("${databasePath.name}-journal")
        return !databasePath.exists() &&
            walPath?.exists() != true &&
            sharedMemoryPath?.exists() != true &&
            journalPath?.exists() != true
    }

    private fun List<BehavioralEventEntity>.matches(
        eventIds: List<UUID>,
        expectedState: BehavioralEventSyncState,
        expectedAttemptCount: Int,
        expectedError: String? = null,
    ): Boolean =
        size == EVENT_COUNT &&
            map(BehavioralEventEntity::id).toSet() == eventIds.map(UUID::toString).toSet() &&
            all { event ->
                event.syncState == expectedState.value &&
                    event.syncAttemptCount == expectedAttemptCount &&
                    event.lastSyncError == expectedError
            }

    private fun List<BehavioralEventEntity>.stateSummary(): String =
        if (isEmpty()) {
            "empty"
        } else {
            groupBy(BehavioralEventEntity::syncState)
                .toSortedMap()
                .entries
                .joinToString("+") { (state, events) -> "$state:${events.size}" }
        }

    private fun RecordedRequest?.matchesEventUpload(eventIds: List<UUID>): Boolean {
        if (this == null ||
            method != "POST" ||
            path != "/v1/events" ||
            getHeader("Authorization") != "Bearer $CONTROLLED_TOKEN"
        ) {
            return false
        }
        val uploadedIds =
            runCatching {
                MnemeApiClient.json
                    .parseToJsonElement(body.readUtf8())
                    .jsonArray
                    .map { event ->
                        event.jsonObject
                            .getValue("event_id")
                            .jsonPrimitive.content
                    }
            }.getOrNull()
        return uploadedIds == eventIds.map(UUID::toString)
    }

    private fun BehavioralEventSyncResult.describe(): String =
        when (this) {
            BehavioralEventSyncResult.Idle -> "idle"
            is BehavioralEventSyncResult.Synced ->
                "synced_${processed}_${accepted}_$duplicates"
            is BehavioralEventSyncResult.Retry -> "retry_$reason"
            is BehavioralEventSyncResult.Failed -> "failed_$reason"
        }

    private fun temporaryFailureResponse(): MockResponse =
        MockResponse()
            .setResponseCode(503)
            .setHeader("Content-Type", "application/json")
            .setBody(
                """{"code":"temporary","message":"controlled failure","request_id":"e4-formal"}""",
            )

    private fun resolveIterations(rawValue: String?): Int {
        val iterations = rawValue?.toIntOrNull() ?: DEFAULT_ITERATIONS
        require(iterations in 1..MAX_ITERATIONS) {
            "$ITERATIONS_ARGUMENT must be an integer from 1 to $MAX_ITERATIONS."
        }
        return iterations
    }

    private fun elapsedMillis(startedAtNanos: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAtNanos) / NANOS_PER_MILLISECOND

    private data class StageObservation(
        val durationMillis: Double,
        val success: Boolean,
        val outcome: String,
        val accepted: Int? = null,
        val duplicates: Int? = null,
        val finalState: String,
    )

    private companion object {
        const val BASE_URL_ARGUMENT = "e4BaseUrl"
        const val TOKEN_ARGUMENT = "e4Token"
        const val PAPER_ID_ARGUMENT = "e4PaperId"
        const val ITERATIONS_ARGUMENT = "e4EventIterations"
        const val FORMAL_FILE = "formal_event_sync_measurements.csv"
        const val DEFAULT_ITERATIONS = 10
        const val MAX_ITERATIONS = 100
        const val EVENT_COUNT = 3
        const val EVENT_CLOCK_MARGIN_MILLIS = 1_000L
        const val MOCK_REQUEST_TIMEOUT_SECONDS = 5L
        const val CONTROLLED_TOKEN = "controlled-e4-token"
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        const val API_503 = "api_503"
        val FORMAL_HEADER =
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
                "event_ids",
            )
    }
}
