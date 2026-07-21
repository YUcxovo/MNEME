package com.mneme.app.data.local

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
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
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

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
