package com.mneme.app.sync

import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.PaperDto
import com.mneme.app.notifications.DigestNotificationPublisher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger

class DigestRefreshCoordinatorTest {
    @Test
    fun newDigest_isCachedByRefresherAndNotifiedOnce() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.digest = digest("digest-new")

            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.Synced("digest-new"), result)
            assertEquals(listOf("digest-new"), notifier.digestIds)
            assertEquals("digest-new", state.lastNotifiedDigestId())
        }

    @Test
    fun sameDigest_doesNotEmitADuplicateNotification() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.digest = digest("digest-current")
            state.markNotified("digest-current")

            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.Synced("digest-current"), result)
            assertTrue(notifier.digestIds.isEmpty())
        }

    @Test
    fun noCompleteDigest_finishesWithoutNotification() =
        runCoordinatorTest { refresher, state, notifier ->
            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.NoCompleteDigest, result)
            assertTrue(notifier.digestIds.isEmpty())
            assertNull(state.lastNotifiedDigestId())
        }

    @Test
    fun deniedNotificationPermission_stillCompletesRefreshWithoutMarkingNotification() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.digest = digest("digest-permission-denied")
            notifier.canNotify = false

            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.Synced("digest-permission-denied"), result)
            assertEquals(listOf("digest-permission-denied"), notifier.digestIds)
            assertNull(state.lastNotifiedDigestId())
        }

    @Test
    fun belowThresholdWeeklyDigest_isCachedWithoutNotification() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.digest = digest("digest-below", relevanceScore = 0.74)

            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.Synced("digest-below"), result)
            assertTrue(notifier.digestIds.isEmpty())
            assertNull(state.lastNotifiedDigestId())
        }

    @Test
    fun nonWeeklyDigest_doesNotNotifyEvenAboveThreshold() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.digest = digest("digest-daily", digestType = "daily")

            val result = coordinator(refresher, state, notifier).refresh()

            assertEquals(DigestSyncResult.Synced("digest-daily"), result)
            assertTrue(notifier.digestIds.isEmpty())
        }

    @Test
    fun transientNetworkFailure_requestsWorkManagerRetry() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.error = IOException("offline")

            assertEquals(DigestSyncResult.Retry, coordinator(refresher, state, notifier).refresh())
        }

    @Test
    fun serverAndRateLimitFailures_requestWorkManagerRetry_butClientFailureDoesNot() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.error = apiError(503)
            assertEquals(DigestSyncResult.Retry, coordinator(refresher, state, notifier).refresh())

            refresher.error = apiError(429)
            assertEquals(DigestSyncResult.Retry, coordinator(refresher, state, notifier).refresh())

            refresher.error = apiError(401)
            assertEquals(DigestSyncResult.Failed, coordinator(refresher, state, notifier).refresh())
        }

    @Test
    fun concurrentRefreshes_areSerializedAndNotifyOnce() =
        runBlocking {
            val refresher = ConcurrentRefresher(digest("digest-concurrent"))
            val state = FakeNotificationState()
            val notifier = FakeNotifier()
            val coordinator = DigestRefreshCoordinator(refresher, state, notifier)

            val results =
                listOf(
                    async(Dispatchers.Default) { coordinator.refresh() },
                    async(Dispatchers.Default) { coordinator.refresh() },
                ).awaitAll()

            assertEquals(
                listOf(
                    DigestSyncResult.Synced("digest-concurrent"),
                    DigestSyncResult.Synced("digest-concurrent"),
                ),
                results,
            )
            assertEquals(1, refresher.maximumConcurrentCalls.get())
            assertEquals(listOf("digest-concurrent"), notifier.digestIds)
        }

    private fun runCoordinatorTest(
        block: suspend (
            FakeRefresher,
            FakeNotificationState,
            FakeNotifier,
        ) -> Unit,
    ) = runBlocking { block(FakeRefresher(), FakeNotificationState(), FakeNotifier()) }

    private fun coordinator(
        refresher: FakeRefresher,
        state: FakeNotificationState,
        notifier: FakeNotifier,
    ) = DigestRefreshCoordinator(refresher, state, notifier)

    private fun digest(
        id: String,
        digestType: String = "weekly",
        relevanceScore: Double = 0.90,
    ) = DigestDto(
        id = id,
        digestType = digestType,
        generatedAt = "2026-08-03T00:00:00Z",
        entries =
            listOf(
                DigestEntryDto(
                    paper = paper(),
                    rank = 1,
                    relevanceScore = relevanceScore,
                    recommendationReason = "Matches the configured research interests.",
                ),
            ),
    )

    private fun paper() =
        PaperDto(
            id = "paper-1",
            arxivId = "2501.00001",
            title = "A test paper",
            authors = listOf("A. Researcher"),
            abstract = "Test abstract.",
            primaryCategory = "cs.AI",
            categories = listOf("cs.AI"),
            pdfUrl = "https://arxiv.org/pdf/2501.00001",
            processingStatus = "ready",
            publishedAt = "2025-01-01T00:00:00Z",
            updatedAt = "2025-01-01T00:00:00Z",
        )

    private fun apiError(statusCode: Int) =
        MnemeApiException(
            statusCode = statusCode,
            errorCode = "upstream_error",
            message = "backend unavailable",
            requestId = null,
        )

    private class FakeRefresher : DigestBriefingRefresher {
        var digest: DigestDto? = null
        var error: Throwable? = null

        override suspend fun refreshLatest(): DigestDto? {
            error?.let { throw it }
            return digest
        }
    }

    private class ConcurrentRefresher(
        private val digest: DigestDto,
    ) : DigestBriefingRefresher {
        private val activeCalls = AtomicInteger()
        val maximumConcurrentCalls = AtomicInteger()

        override suspend fun refreshLatest(): DigestDto {
            val active = activeCalls.incrementAndGet()
            maximumConcurrentCalls.accumulateAndGet(active, ::maxOf)
            return try {
                delay(CONCURRENT_REFRESH_DELAY_MILLIS)
                digest
            } finally {
                activeCalls.decrementAndGet()
            }
        }

        private companion object {
            const val CONCURRENT_REFRESH_DELAY_MILLIS = 50L
        }
    }

    private class FakeNotificationState : DigestNotificationState {
        private var digestId: String? = null

        override fun lastNotifiedDigestId(): String? = digestId

        override fun markNotified(digestId: String) {
            this.digestId = digestId
        }
    }

    private class FakeNotifier : DigestNotificationPublisher {
        var canNotify = true
        val digestIds = mutableListOf<String>()

        override fun showNewDigest(
            digestId: String,
            digestTitle: String,
        ): Boolean {
            digestIds += digestId
            return canNotify
        }
    }
}
