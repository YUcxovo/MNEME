package com.mneme.app.data.local

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.local.entity.CacheMetadataEntity
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.local.entity.PaperEntity
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PreferencesDto
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class MnemeDatabaseTest {
    private lateinit var database: MnemeDatabase

    @Before
    fun createDatabase() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database =
            Room
                .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }

    @After
    fun closeDatabase() {
        database.close()
    }

    @Test
    fun paperDao_upsertAndObserve_returnsNewestFirst() =
        runBlocking {
            database.paperDao().upsertAll(
                listOf(
                    paper(id = "older", arxivId = "2401.00001", updatedAt = 1),
                    paper(id = "newer", arxivId = "2401.00002", updatedAt = 2),
                ),
            )

            val papers = database.paperDao().observeAll().first()

            assertEquals(listOf("newer", "older"), papers.map(PaperEntity::id))
        }

    @Test
    fun cacheDaos_retainRecentAndOpenedContent() =
        runBlocking {
            database.paperDao().upsertAll(
                listOf(
                    paper(id = "recent", arxivId = "2401.00003", updatedAt = 90),
                    paper(id = "expired", arxivId = "2401.00004", updatedAt = 10),
                    paper(id = "opened", arxivId = "2401.00005", updatedAt = 10),
                ),
            )
            database.paperDao().markOpened(id = "opened", openedAtEpochMillis = 80)
            database.digestDao().upsertAll(
                listOf(
                    DigestEntity(
                        id = "old-digest",
                        title = "Old",
                        summary = "Old summary",
                        digestType = "daily",
                        generatedAtEpochMillis = 10,
                    ),
                    DigestEntity(
                        id = "new-digest",
                        title = "New",
                        summary = "New summary",
                        digestType = "daily",
                        generatedAtEpochMillis = 90,
                    ),
                ),
            )

            assertEquals(1, database.paperDao().deleteExpired(50, 50))
            assertEquals(1, database.digestDao().deleteOlderThan(50))
            database.cacheMetadataDao().upsert(
                CacheMetadataEntity(lastSuccessfulRefreshAtEpochMillis = 100),
            )

            assertEquals(
                listOf("recent", "opened"),
                database
                    .paperDao()
                    .observeAll()
                    .first()
                    .map(PaperEntity::id),
            )
            assertEquals(
                listOf("new-digest"),
                database
                    .digestDao()
                    .observeAll()
                    .first()
                    .map(DigestEntity::id),
            )
            assertEquals(
                100L,
                database
                    .cacheMetadataDao()
                    .observe()
                    .first()
                    ?.lastSuccessfulRefreshAtEpochMillis,
            )
        }

    @Test
    fun offlineCachePrune_retainsRecentAndRecentlyOpenedContentAfterReconnect() =
        runBlocking {
            val now = TimeUnit.DAYS.toMillis(100)
            val repository =
                OfflineCacheRepository(
                    paperDao = database.paperDao(),
                    digestDao = database.digestDao(),
                    cacheMetadataDao = database.cacheMetadataDao(),
                )
            database.paperDao().upsertAll(
                listOf(
                    paper("recent", "2401.00011", now - TimeUnit.DAYS.toMillis(13)),
                    paper("opened", "2401.00012", now - TimeUnit.DAYS.toMillis(20)),
                    paper("expired", "2401.00013", now - TimeUnit.DAYS.toMillis(15)),
                ),
            )
            repository.markPaperOpened("opened", now - TimeUnit.DAYS.toMillis(29))
            database.digestDao().upsertAll(
                listOf(
                    DigestEntity(
                        id = "recent-digest",
                        title = "Recent",
                        summary = "Summary",
                        digestType = "daily",
                        generatedAtEpochMillis = now - TimeUnit.DAYS.toMillis(13),
                    ),
                    DigestEntity(
                        id = "expired-digest",
                        title = "Expired",
                        summary = "Summary",
                        digestType = "daily",
                        generatedAtEpochMillis = now - TimeUnit.DAYS.toMillis(15),
                    ),
                ),
            )

            repository.recordSuccessfulRefresh(now)
            val result = repository.pruneExpiredContent(now)

            assertEquals(1, result.removedPapers)
            assertEquals(1, result.removedDigests)
            assertEquals(
                listOf("recent", "opened"),
                database
                    .paperDao()
                    .observeAll()
                    .first()
                    .map(PaperEntity::id),
            )
            assertEquals(
                listOf("recent-digest"),
                database
                    .digestDao()
                    .observeAll()
                    .first()
                    .map(DigestEntity::id),
            )
            assertEquals(now, repository.observeMetadata().first()?.lastSuccessfulRefreshAtEpochMillis)
        }

    @Test
    fun skeletalCache_roundTripsExactDigestOrderReasonsAndPreferences() =
        runBlocking {
            val cache = RoomSkeletalCache(database, Json { ignoreUnknownKeys = true })
            val firstPaper = paperDto(id = "paper-1", title = "First paper")
            val secondPaper = paperDto(id = "paper-2", title = "Second paper")

            cache.storeBriefing(
                preferences =
                    PreferencesDto(
                        topics = listOf("retrieval", "mobile systems"),
                        followedAuthors = listOf("A. Researcher"),
                        modelVersion = 3,
                        updatedAt = "2026-07-22T08:00:00Z",
                    ),
                digest =
                    DigestDto(
                        id = "digest-live",
                        digestType = "manual",
                        generatedAt = "2026-07-22T08:00:00Z",
                        entries =
                            listOf(
                                digestEntry(secondPaper, rank = 2, reason = "Second reason"),
                                digestEntry(firstPaper, rank = 1, reason = "First reason"),
                            ),
                    ),
                refreshedAtEpochMillis = 500,
            )

            val cached = checkNotNull(cache.getBriefing())

            assertEquals(listOf("paper-1", "paper-2"), cached.papers.map { it.id })
            assertEquals("First reason", cached.recommendationReasons["paper-1"])
            assertEquals(listOf("retrieval", "mobile systems"), cached.interests)
            assertEquals(500L, cached.refreshedAtEpochMillis)
            assertEquals(listOf("A. Researcher"), cached.papers.first().authors)
        }

    @Test
    fun behavioralEventRepository_recordsAndTracksRetryState() =
        runBlocking {
            val eventId = UUID.fromString("8f0a1d3b-cc41-43f0-97c2-c175341ef07c")
            val paperId = UUID.fromString("2d3f275d-2f4f-4144-a9fd-a2cbe8f12c88")
            val repository =
                BehavioralEventRepository(
                    behavioralEventDao = database.behavioralEventDao(),
                    idGenerator = { eventId },
                )

            repository.record(
                type = BehavioralEventType.PAPER_OPENED,
                paperId = paperId,
                occurredAtEpochMillis = 20,
                durationMillis = 500,
            )

            val queued = repository.observeAll().first().single()
            assertEquals(eventId.toString(), queued.id)
            assertEquals("paper_opened", queued.eventType)
            assertEquals(paperId.toString(), queued.paperId)
            assertEquals(500L, queued.durationMillis)

            val batch =
                repository.reservePendingBatch(
                    limit = 1,
                    attemptedAtEpochMillis = 30,
                    staleBeforeEpochMillis = 0,
                )
            assertEquals(listOf(eventId.toString()), batch.map(BehavioralEventEntity::id))
            assertEquals(BehavioralEventSyncState.IN_FLIGHT.value, batch.single().syncState)
            assertEquals(1, batch.single().syncAttemptCount)

            repository.returnBatchToPending(listOf(eventId), "network")

            val pending = repository.observeAll().first().single()
            assertEquals(BehavioralEventSyncState.PENDING.value, pending.syncState)
            assertEquals(1, pending.syncAttemptCount)
            assertEquals("network", pending.lastSyncError)
        }

    @Test
    fun behavioralEventRepository_requeuesOnlyStaleInFlightEvents() =
        runBlocking {
            val staleId = UUID.fromString("1332d484-3d95-4596-a99f-5eb01bb30388")
            val freshId = UUID.fromString("38372d72-14ff-4ec0-8d4c-c8ebdb57dfc9")
            val paperId = UUID.fromString("130617f3-4632-4d03-abd6-693495965a31")
            database.behavioralEventDao().insert(
                BehavioralEventEntity(
                    id = staleId.toString(),
                    eventType = BehavioralEventType.PAPER_SAVED.wireValue,
                    paperId = paperId.toString(),
                    occurredAtEpochMillis = 10,
                    syncState = BehavioralEventSyncState.IN_FLIGHT.value,
                    syncAttemptCount = 1,
                    lastSyncAttemptAtEpochMillis = 20,
                ),
            )
            database.behavioralEventDao().insert(
                BehavioralEventEntity(
                    id = freshId.toString(),
                    eventType = BehavioralEventType.QUESTION_ASKED.wireValue,
                    paperId = paperId.toString(),
                    occurredAtEpochMillis = 30,
                    syncState = BehavioralEventSyncState.IN_FLIGHT.value,
                    syncAttemptCount = 1,
                    lastSyncAttemptAtEpochMillis = 90,
                ),
            )
            val repository = BehavioralEventRepository(database.behavioralEventDao())

            val batch =
                repository.reservePendingBatch(
                    limit = 10,
                    attemptedAtEpochMillis = 100,
                    staleBeforeEpochMillis = 50,
                )

            assertEquals(listOf(staleId.toString()), batch.map(BehavioralEventEntity::id))
            assertEquals(2, batch.single().syncAttemptCount)
            val storedById = repository.observeAll().first().associateBy(BehavioralEventEntity::id)
            assertEquals(
                BehavioralEventSyncState.IN_FLIGHT.value,
                storedById.getValue(freshId.toString()).syncState,
            )
            assertEquals(90L, storedById.getValue(freshId.toString()).lastSyncAttemptAtEpochMillis)
        }

    @Test
    fun behavioralEventRepository_rejectsPayloadsOutsideTheFrozenContract() =
        runBlocking {
            val repository = BehavioralEventRepository(database.behavioralEventDao())
            val paperId = UUID.fromString("130617f3-4632-4d03-abd6-693495965a31")

            assertIllegalArgument {
                repository.record(
                    type = BehavioralEventType.PAPER_SAVED,
                    paperId = null,
                    occurredAtEpochMillis = 10,
                )
            }
            assertIllegalArgument {
                repository.record(
                    type = BehavioralEventType.DIGEST_DISMISSED,
                    paperId = paperId,
                    occurredAtEpochMillis = 10,
                )
            }
            assertIllegalArgument {
                repository.record(
                    type = BehavioralEventType.PAPER_SAVED,
                    paperId = paperId,
                    occurredAtEpochMillis = 10,
                    durationMillis = 50,
                )
            }
            assertIllegalArgument {
                repository.record(
                    type = BehavioralEventType.PAPER_OPENED,
                    paperId = paperId,
                    occurredAtEpochMillis = -1,
                )
            }
            assertIllegalArgument {
                repository.record(
                    type = BehavioralEventType.PAPER_OPENED,
                    paperId = paperId,
                    occurredAtEpochMillis = 10,
                    durationMillis = Int.MAX_VALUE.toLong() + 1,
                )
            }
        }

    private suspend fun assertIllegalArgument(block: suspend () -> Unit) {
        var rejected = false
        try {
            block()
        } catch (_: IllegalArgumentException) {
            rejected = true
        }
        assertTrue("Expected the event payload to be rejected.", rejected)
    }

    private fun paper(
        id: String,
        arxivId: String,
        updatedAt: Long,
    ) = PaperEntity(
        id = id,
        arxivId = arxivId,
        title = "Paper $id",
        authorsJson = "[]",
        abstractText = "Abstract",
        primaryCategory = "cs.HC",
        pdfUrl = null,
        processingStatus = "ready",
        updatedAtEpochMillis = updatedAt,
    )

    private fun paperDto(
        id: String,
        title: String,
    ) = PaperDto(
        id = id,
        arxivId = "2607.$id",
        title = title,
        authors = listOf("A. Researcher"),
        abstract = "Abstract for $title",
        primaryCategory = "cs.IR",
        categories = listOf("cs.IR"),
        pdfUrl = "https://arxiv.org/pdf/2607.00001",
        processingStatus = "ready",
        publishedAt = "2026-07-21T08:00:00Z",
        updatedAt = "2026-07-22T08:00:00Z",
    )

    private fun digestEntry(
        paper: PaperDto,
        rank: Int,
        reason: String,
    ) = DigestEntryDto(
        paper = paper,
        rank = rank,
        relevanceScore = 0.8,
        recommendationReason = reason,
    )
}
