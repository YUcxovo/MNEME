package com.mneme.app.sync

import android.Manifest
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.PackageManager
import android.os.Build
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.PaperDto
import com.mneme.app.notifications.DigestNotifier
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DigestNotificationDeliveryTest {
    @Test
    fun deniedNotificationPermission_keepsDigestRefreshSuccessfulWithoutRecordingNotification() =
        runBlocking {
            val state = InMemoryNotificationState()
            val context =
                DeniedNotificationContext(
                    ApplicationProvider.getApplicationContext(),
                )
            assumeTrue(Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            assertEquals(
                PackageManager.PERMISSION_DENIED,
                context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS),
            )

            val coordinator =
                DigestRefreshCoordinator(
                    refresher = FakeRefresher,
                    notificationState = state,
                    notifier = DigestNotifier(context),
                )

            val result = coordinator.refresh()

            assertEquals(DigestSyncResult.Synced("api34-digest"), result)
            assertNull(state.lastNotifiedDigestId())
        }

    private class DeniedNotificationContext(
        base: Context,
    ) : ContextWrapper(base) {
        override fun checkSelfPermission(permission: String): Int =
            if (permission == Manifest.permission.POST_NOTIFICATIONS) {
                PackageManager.PERMISSION_DENIED
            } else {
                super.checkSelfPermission(permission)
            }

        override fun checkPermission(
            permission: String,
            pid: Int,
            uid: Int,
        ): Int =
            if (permission == Manifest.permission.POST_NOTIFICATIONS) {
                PackageManager.PERMISSION_DENIED
            } else {
                super.checkPermission(permission, pid, uid)
            }
    }

    private object FakeRefresher : DigestBriefingRefresher {
        override suspend fun refreshLatest() =
            DigestDto(
                id = "api34-digest",
                digestType = "weekly",
                generatedAt = "2026-08-03T00:00:00Z",
                entries =
                    listOf(
                        DigestEntryDto(
                            paper =
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
                                ),
                            rank = 1,
                            relevanceScore = 0.90,
                            recommendationReason = "Matches the configured research interests.",
                        ),
                    ),
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
