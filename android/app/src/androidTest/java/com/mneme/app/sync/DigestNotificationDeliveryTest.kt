package com.mneme.app.sync

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.network.DigestDto
import com.mneme.app.notifications.DigestNotifier
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DigestNotificationDeliveryTest {
    @Test
    fun deniedNotificationPermission_keepsDigestRefreshSuccessfulWithoutRecordingNotification() =
        runBlocking {
            val state = InMemoryNotificationState()
            val coordinator =
                DigestRefreshCoordinator(
                    refresher = FakeRefresher,
                    notificationState = state,
                    notifier = DigestNotifier(ApplicationProvider.getApplicationContext()),
                )

            val result = coordinator.refresh()

            assertEquals(DigestSyncResult.Synced("api34-digest"), result)
            assertNull(state.lastNotifiedDigestId())
        }

    private object FakeRefresher : DigestBriefingRefresher {
        override suspend fun refreshLatest() =
            DigestDto(
                id = "api34-digest",
                digestType = "daily",
                generatedAt = "2026-08-03T00:00:00Z",
                entries = emptyList(),
            )
    }

    private class InMemoryNotificationState : DigestNotificationState {
        private var digestId: String? = null

        override fun lastNotifiedDigestId(): String? = digestId

        override fun markNotified(digestId: String) {
            this.digestId = digestId
        }
    }
}
