@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.data.behavior.BehavioralEventSyncCoordinator
import com.mneme.app.data.behavior.BehavioralEventSyncResult
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.BehavioralEventType
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.network.BehavioralEventRemoteDataSource
import com.mneme.app.data.network.EventIngestionResultDto
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.network.UserEventDto
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.ui.model.ContentOrigin
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException
import java.util.ArrayDeque
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class E4LiveBackendClosedLoopTest {
    @Test
    fun recordPersistedQueueThroughLiveBackendAndClientReadback() =
        runBlocking {
            val arguments = InstrumentationRegistry.getArguments()
            val baseUrl = arguments.getString(BASE_URL_ARGUMENT)
            val token = arguments.getString(TOKEN_ARGUMENT)
            assumeTrue(
                "Live E4 evaluation requires explicit backend URL and token arguments.",
                !baseUrl.isNullOrBlank() && !token.isNullOrBlank(),
            )

            E4MeasurementFiles.resetCsv(LIVE_FILE, LIVE_HEADER)
            val remote = MnemeApiClient.create(requireNotNull(baseUrl), requireNotNull(token))
            val paper =
                remote.listPapers(limit = 1).items.firstOrNull()
                    ?: error("The live backend needs at least one paper for the E4 event trace.")
            var failures = 0

            repeat(LIVE_ITERATIONS) { index ->
                val eventIds = List(EVENT_COUNT) { UUID.randomUUID() }
                val occurredAt = System.currentTimeMillis() - 1_000
                val primaryDatabase = createDatabase()
                try {
                    val store =
                        BehavioralEventRepository(
                            behavioralEventDao = primaryDatabase.behavioralEventDao(),
                            idGenerator = ArrayDeque(eventIds)::removeFirst,
                        )
                    val queueStartedAt = SystemClock.elapsedRealtimeNanos()
                    recordThreeEvents(store, UUID.fromString(paper.id), occurredAt)
                    val queued = store.observeAll().first()
                    failures +=
                        record(
                            scenario = "live_queue_write",
                            iteration = index + 1,
                            durationMillis = elapsedMillis(queueStartedAt),
                            success =
                                queued.size == EVENT_COUNT &&
                                    queued.all { event ->
                                        event.syncState == BehavioralEventSyncState.PENDING.value
                                    },
                            outcome = "pending",
                        )

                    val failureCoordinator =
                        BehavioralEventSyncCoordinator(
                            store = store,
                            remote = ControlledNetworkFailure,
                        )
                    val failureStartedAt = SystemClock.elapsedRealtimeNanos()
                    val failure = failureCoordinator.syncPending()
                    val afterFailure = store.observeAll().first()
                    failures +=
                        record(
                            scenario = "controlled_failure_before_live_retry",
                            iteration = index + 1,
                            durationMillis = elapsedMillis(failureStartedAt),
                            success =
                                failure is BehavioralEventSyncResult.Retry &&
                                    afterFailure.all { event ->
                                        event.syncState == BehavioralEventSyncState.PENDING.value
                                    },
                            outcome = failure::class.java.simpleName,
                        )

                    val liveCoordinator =
                        BehavioralEventSyncCoordinator(
                            store = store,
                            remote = remote,
                        )
                    val liveStartedAt = SystemClock.elapsedRealtimeNanos()
                    val liveResult = liveCoordinator.syncPending()
                    val afterLive = store.observeAll().first()
                    val liveSuccess =
                        liveResult ==
                            BehavioralEventSyncResult.Synced(
                                processed = EVENT_COUNT,
                                accepted = EVENT_COUNT,
                                duplicates = 0,
                            ) &&
                            afterLive.all { event ->
                                event.syncState == BehavioralEventSyncState.SYNCED.value
                            }
                    failures +=
                        record(
                            scenario = "live_retry_upload",
                            iteration = index + 1,
                            durationMillis = elapsedMillis(liveStartedAt),
                            success = liveSuccess,
                            outcome = liveResult::class.java.simpleName,
                            accepted = (liveResult as? BehavioralEventSyncResult.Synced)?.accepted,
                            duplicates = (liveResult as? BehavioralEventSyncResult.Synced)?.duplicates,
                        )

                    val duplicateDatabase = createDatabase()
                    try {
                        val duplicateStore =
                            BehavioralEventRepository(
                                behavioralEventDao = duplicateDatabase.behavioralEventDao(),
                                idGenerator = ArrayDeque(eventIds)::removeFirst,
                            )
                        recordThreeEvents(duplicateStore, UUID.fromString(paper.id), occurredAt)
                        val duplicateCoordinator =
                            BehavioralEventSyncCoordinator(
                                store = duplicateStore,
                                remote = remote,
                            )
                        val duplicateStartedAt = SystemClock.elapsedRealtimeNanos()
                        val duplicateResult = duplicateCoordinator.syncPending()
                        val duplicateSuccess =
                            duplicateResult ==
                                BehavioralEventSyncResult.Synced(
                                    processed = EVENT_COUNT,
                                    accepted = 0,
                                    duplicates = EVENT_COUNT,
                                )
                        failures +=
                            record(
                                scenario = "live_duplicate_replay",
                                iteration = index + 1,
                                durationMillis = elapsedMillis(duplicateStartedAt),
                                success = duplicateSuccess,
                                outcome = duplicateResult::class.java.simpleName,
                                accepted =
                                    (duplicateResult as? BehavioralEventSyncResult.Synced)?.accepted,
                                duplicates =
                                    (duplicateResult as? BehavioralEventSyncResult.Synced)?.duplicates,
                            )
                    } finally {
                        duplicateDatabase.close()
                    }

                    val readbackStartedAt = SystemClock.elapsedRealtimeNanos()
                    val preferences = remote.getPreferences()
                    val clientRepository =
                        NetworkSkeletalDataRepository(
                            remote = remote,
                            cache = RoomSkeletalCache(primaryDatabase, MnemeApiClient.json),
                        )
                    val briefing = clientRepository.loadBriefing()
                    failures +=
                        record(
                            scenario = "live_client_readback",
                            iteration = index + 1,
                            durationMillis = elapsedMillis(readbackStartedAt),
                            success = briefing.disclosure.origin == ContentOrigin.LIVE_BACKEND,
                            outcome = "live_briefing_ui_model_returned",
                            digestEntries = briefing.papers.size,
                            preferenceModelVersion = preferences.modelVersion,
                            briefingOrigin = briefing.disclosure.origin.name,
                        )
                } finally {
                    primaryDatabase.close()
                }
            }

            assertEquals("Every live closed-loop stage must complete.", 0, failures)
        }

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

    private fun createDatabase(): MnemeDatabase {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Room
            .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    private fun record(
        scenario: String,
        iteration: Int,
        durationMillis: Double,
        success: Boolean,
        outcome: String,
        accepted: Int? = null,
        duplicates: Int? = null,
        digestEntries: Int? = null,
        preferenceModelVersion: Int? = null,
        briefingOrigin: String? = null,
    ): Int {
        E4MeasurementFiles.appendCsv(
            LIVE_FILE,
            listOf(
                "event_sync",
                scenario,
                iteration,
                EVENT_COUNT,
                durationMillis,
                success,
                outcome,
                accepted,
                duplicates,
                digestEntries,
                preferenceModelVersion,
                briefingOrigin,
            ),
        )
        return if (success) 0 else 1
    }

    private fun elapsedMillis(startedAtNanos: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAtNanos) / NANOS_PER_MILLISECOND

    private object ControlledNetworkFailure : BehavioralEventRemoteDataSource {
        override suspend fun uploadEvents(events: List<UserEventDto>): EventIngestionResultDto =
            throw IOException("Controlled pre-upload failure.")
    }

    private companion object {
        const val BASE_URL_ARGUMENT = "e4BaseUrl"
        const val TOKEN_ARGUMENT = "e4Token"
        const val LIVE_FILE = "live_event_closed_loop.csv"
        const val LIVE_ITERATIONS = 5
        const val EVENT_COUNT = 3
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        val LIVE_HEADER =
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
                "digest_entries",
                "preference_model_version",
                "briefing_origin",
            )
    }
}
