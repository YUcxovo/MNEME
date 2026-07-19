package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import kotlinx.coroutines.flow.Flow

@Dao
interface BehavioralEventDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(event: BehavioralEventEntity): Long

    @Query(
        "SELECT * FROM behavioral_events " +
            "WHERE sync_state = :syncState ORDER BY occurred_at ASC LIMIT :limit",
    )
    suspend fun pendingBatch(
        limit: Int,
        syncState: String = BehavioralEventSyncState.PENDING.value,
    ): List<BehavioralEventEntity>

    @Query("SELECT * FROM behavioral_events ORDER BY occurred_at ASC")
    fun observeAll(): Flow<List<BehavioralEventEntity>>

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, " +
            "sync_attempt_count = sync_attempt_count + 1, " +
            "last_sync_attempt_at = :attemptedAtEpochMillis, last_sync_error = NULL " +
            "WHERE id IN (:eventIds)",
    )
    suspend fun markInFlight(
        eventIds: List<String>,
        attemptedAtEpochMillis: Long,
        syncState: String = BehavioralEventSyncState.IN_FLIGHT.value,
    ): Int

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, last_sync_error = :error " +
            "WHERE id IN (:eventIds)",
    )
    suspend fun markPending(
        eventIds: List<String>,
        error: String?,
        syncState: String = BehavioralEventSyncState.PENDING.value,
    ): Int

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, last_sync_error = NULL " +
            "WHERE id IN (:eventIds)",
    )
    suspend fun markSynced(
        eventIds: List<String>,
        syncState: String = BehavioralEventSyncState.SYNCED.value,
    ): Int
}
