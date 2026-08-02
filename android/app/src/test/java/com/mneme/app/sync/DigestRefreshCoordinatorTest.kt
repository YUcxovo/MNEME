package com.mneme.app.sync

import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.notifications.DigestNotificationPublisher
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

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
    fun transientNetworkFailure_requestsWorkManagerRetry() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.error = IOException("offline")

            assertEquals(DigestSyncResult.Retry, coordinator(refresher, state, notifier).refresh())
        }

    @Test
    fun serverFailure_requestsWorkManagerRetry_butClientFailureDoesNot() =
        runCoordinatorTest { refresher, state, notifier ->
            refresher.error = apiError(503)
            assertEquals(DigestSyncResult.Retry, coordinator(refresher, state, notifier).refresh())

            refresher.error = apiError(401)
            assertEquals(DigestSyncResult.Failed, coordinator(refresher, state, notifier).refresh())
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

    private fun digest(id: String) =
        DigestDto(
            id = id,
            digestType = "daily",
            generatedAt = "2026-08-03T00:00:00Z",
            entries = emptyList(),
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
