package com.mneme.app.data.local

import com.mneme.app.data.local.dao.CacheMetadataDao
import com.mneme.app.data.local.dao.DigestDao
import com.mneme.app.data.local.dao.PaperDao
import com.mneme.app.data.local.entity.CacheMetadataEntity
import kotlinx.coroutines.flow.Flow
import java.util.concurrent.TimeUnit

object OfflineCachePolicy {
    const val RECENT_CONTENT_RETENTION_DAYS = 14L
    const val OPENED_PAPER_RETENTION_DAYS = 30L
    private val recentContentRetentionMillis = TimeUnit.DAYS.toMillis(RECENT_CONTENT_RETENTION_DAYS)
    private val openedPaperRetentionMillis = TimeUnit.DAYS.toMillis(OPENED_PAPER_RETENTION_DAYS)

    fun recentContentCutoff(nowEpochMillis: Long): Long = nowEpochMillis - recentContentRetentionMillis

    fun openedPaperCutoff(nowEpochMillis: Long): Long = nowEpochMillis - openedPaperRetentionMillis
}

class OfflineCacheRepository(
    private val paperDao: PaperDao,
    private val digestDao: DigestDao,
    private val cacheMetadataDao: CacheMetadataDao,
) {
    fun observeMetadata(): Flow<CacheMetadataEntity?> = cacheMetadataDao.observe()

    suspend fun markPaperOpened(
        paperId: String,
        openedAtEpochMillis: Long,
    ) {
        paperDao.markOpened(paperId, openedAtEpochMillis)
    }

    suspend fun recordSuccessfulRefresh(refreshedAtEpochMillis: Long) {
        cacheMetadataDao.upsert(
            CacheMetadataEntity(lastSuccessfulRefreshAtEpochMillis = refreshedAtEpochMillis),
        )
    }

    suspend fun pruneExpiredContent(nowEpochMillis: Long): CachePruneResult =
        CachePruneResult(
            removedDigests = digestDao.deleteOlderThan(OfflineCachePolicy.recentContentCutoff(nowEpochMillis)),
            removedPapers =
                paperDao.deleteExpired(
                    recentPaperCutoffEpochMillis = OfflineCachePolicy.recentContentCutoff(nowEpochMillis),
                    openedPaperCutoffEpochMillis = OfflineCachePolicy.openedPaperCutoff(nowEpochMillis),
                ),
        )
}

data class CachePruneResult(
    val removedDigests: Int,
    val removedPapers: Int,
)
