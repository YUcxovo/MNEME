package com.mneme.app.sync

import com.mneme.app.data.local.SkeletalCache
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.MnemeRemoteDataSource
import com.mneme.app.notifications.DigestNotificationPublisher
import kotlinx.serialization.SerializationException
import java.io.IOException

interface DigestNotificationState {
    fun lastNotifiedDigestId(): String?

    fun markNotified(digestId: String)
}

class DigestRefreshCoordinator(
    private val refresher: DigestBriefingRefresher,
    private val notificationState: DigestNotificationState,
    private val notifier: DigestNotificationPublisher,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) {
    @Suppress("SwallowedException") // Worker results intentionally avoid persisting or exposing transport details.
    suspend fun refresh(): DigestSyncResult =
        try {
            val digest = refresher.refreshLatest() ?: return DigestSyncResult.NoCompleteDigest
            notifyIfNew(digest)
            DigestSyncResult.Synced(digest.id)
        } catch (error: MnemeApiException) {
            if (error.statusCode >= SERVER_ERROR_STATUS) DigestSyncResult.Retry else DigestSyncResult.Failed
        } catch (error: IOException) {
            DigestSyncResult.Retry
        } catch (error: SerializationException) {
            DigestSyncResult.Failed
        }

    private fun notifyIfNew(digest: DigestDto) {
        if (notificationState.lastNotifiedDigestId() == digest.id) return
        if (notifier.showNewDigest(digest.id, digest.notificationTitle())) {
            notificationState.markNotified(digest.id)
        }
    }

    private companion object {
        const val SERVER_ERROR_STATUS = 500
    }
}

interface DigestBriefingRefresher {
    suspend fun refreshLatest(): DigestDto?
}

class LiveDigestBriefingRefresher(
    private val remote: MnemeRemoteDataSource,
    private val cache: SkeletalCache,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) : DigestBriefingRefresher {
    override suspend fun refreshLatest(): DigestDto? {
        val digest = remote.listDigests(limit = LATEST_DIGEST_LIMIT).items.firstOrNull() ?: return null
        cache.storeBriefing(remote.getPreferences(), digest, nowEpochMillis())
        return digest
    }

    private companion object {
        const val LATEST_DIGEST_LIMIT = 1
    }
}

sealed interface DigestSyncResult {
    data class Synced(
        val digestId: String,
    ) : DigestSyncResult

    data object NoCompleteDigest : DigestSyncResult

    data object Retry : DigestSyncResult

    data object Failed : DigestSyncResult
}

private fun DigestDto.notificationTitle(): String =
    when (digestType) {
        "weekly" -> "Your weekly research briefing is ready"
        "manual" -> "Your updated research briefing is ready"
        else -> "Your research briefing is ready"
    }
