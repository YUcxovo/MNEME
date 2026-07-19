package com.mneme.app.data.local

import com.mneme.app.data.local.dao.BehavioralEventDao
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import kotlinx.coroutines.flow.Flow
import java.util.UUID

enum class BehavioralEventType {
    OPEN,
    SAVE,
    SKIP,
    SHARE,
    QUESTION,
    TIME_SPENT,
}

class BehavioralEventRepository(
    private val behavioralEventDao: BehavioralEventDao,
    private val idGenerator: () -> String = { UUID.randomUUID().toString() },
) {
    fun observeAll(): Flow<List<BehavioralEventEntity>> = behavioralEventDao.observeAll()

    suspend fun record(
        type: BehavioralEventType,
        paperId: String?,
        occurredAtEpochMillis: Long,
        durationMillis: Long? = null,
    ): String {
        require(type != BehavioralEventType.TIME_SPENT || durationMillis != null) {
            "TIME_SPENT events require a duration."
        }
        require(durationMillis == null || durationMillis >= 0) {
            "Event duration cannot be negative."
        }

        val event =
            BehavioralEventEntity(
                id = idGenerator(),
                eventType = type.name.lowercase(),
                paperId = paperId,
                occurredAtEpochMillis = occurredAtEpochMillis,
                durationMillis = durationMillis,
            )
        behavioralEventDao.insert(event)
        return event.id
    }

    suspend fun reservePendingBatch(
        limit: Int,
        attemptedAtEpochMillis: Long,
    ): List<BehavioralEventEntity> {
        require(limit > 0) { "Batch limit must be positive." }
        val batch = behavioralEventDao.pendingBatch(limit)
        if (batch.isNotEmpty()) {
            behavioralEventDao.markInFlight(batch.map(BehavioralEventEntity::id), attemptedAtEpochMillis)
        }
        return batch
    }

    suspend fun markBatchSynced(eventIds: List<String>) {
        if (eventIds.isNotEmpty()) {
            behavioralEventDao.markSynced(eventIds)
        }
    }

    suspend fun returnBatchToPending(
        eventIds: List<String>,
        error: String?,
    ) {
        if (eventIds.isNotEmpty()) {
            behavioralEventDao.markPending(eventIds, error)
        }
    }

    fun pendingState(): String = BehavioralEventSyncState.PENDING.value
}
