package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import kotlinx.coroutines.flow.Flow

@Dao
abstract class BehavioralEventDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    abstract suspend fun insert(event: BehavioralEventEntity): Long

    @Query(
        "SELECT * FROM behavioral_events " +
            "WHERE sync_state = :syncState ORDER BY occurred_at ASC LIMIT :limit",
    )
    protected abstract suspend fun pendingBatch(
        limit: Int,
        syncState: String = BehavioralEventSyncState.PENDING.value,
    ): List<BehavioralEventEntity>

    @Query("SELECT * FROM behavioral_events ORDER BY occurred_at ASC")
    abstract fun observeAll(): Flow<List<BehavioralEventEntity>>

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, " +
            "sync_attempt_count = sync_attempt_count + 1, " +
            "last_sync_attempt_at = :attemptedAtEpochMillis, last_sync_error = NULL " +
            "WHERE id IN (:eventIds) AND sync_state = :pendingState",
    )
    protected abstract suspend fun markInFlight(
        eventIds: List<String>,
        attemptedAtEpochMillis: Long,
        syncState: String = BehavioralEventSyncState.IN_FLIGHT.value,
        pendingState: String = BehavioralEventSyncState.PENDING.value,
    ): Int

    @Query(
        "UPDATE behavioral_events SET sync_state = :pendingState, " +
            "last_sync_error = :staleError WHERE sync_state = :inFlightState AND " +
            "(last_sync_attempt_at IS NULL OR last_sync_attempt_at <= :staleBeforeEpochMillis)",
    )
    protected abstract suspend fun requeueStaleInFlight(
        staleBeforeEpochMillis: Long,
        staleError: String = STALE_IN_FLIGHT_ERROR,
        inFlightState: String = BehavioralEventSyncState.IN_FLIGHT.value,
        pendingState: String = BehavioralEventSyncState.PENDING.value,
    ): Int

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, last_sync_error = :error " +
            "WHERE id IN (:eventIds) AND sync_state = :inFlightState",
    )
    abstract suspend fun markPending(
        eventIds: List<String>,
        error: String?,
        syncState: String = BehavioralEventSyncState.PENDING.value,
        inFlightState: String = BehavioralEventSyncState.IN_FLIGHT.value,
    ): Int

    @Query(
        "UPDATE behavioral_events SET sync_state = :syncState, last_sync_error = NULL " +
            "WHERE id IN (:eventIds) AND sync_state = :inFlightState",
    )
    abstract suspend fun markSynced(
        eventIds: List<String>,
        syncState: String = BehavioralEventSyncState.SYNCED.value,
        inFlightState: String = BehavioralEventSyncState.IN_FLIGHT.value,
    ): Int

    @Transaction
    open suspend fun reservePendingBatch(
        limit: Int,
        attemptedAtEpochMillis: Long,
        staleBeforeEpochMillis: Long,
    ): List<BehavioralEventEntity> {
        requeueStaleInFlight(staleBeforeEpochMillis)
        val batch = pendingBatch(limit)
        if (batch.isEmpty()) return emptyList()

        val updated = markInFlight(batch.map(BehavioralEventEntity::id), attemptedAtEpochMillis)
        check(updated == batch.size) { "Behavioral event reservation lost its pending batch." }
        return batch.map { event ->
            event.copy(
                syncState = BehavioralEventSyncState.IN_FLIGHT.value,
                syncAttemptCount = event.syncAttemptCount + 1,
                lastSyncAttemptAtEpochMillis = attemptedAtEpochMillis,
                lastSyncError = null,
            )
        }
    }

    companion object {
        const val STALE_IN_FLIGHT_ERROR = "stale_in_flight"
    }
}
