package com.mneme.app.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "behavioral_events",
    indices = [Index(value = ["sync_state", "occurred_at"])],
)
data class BehavioralEventEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "event_type") val eventType: String,
    @ColumnInfo(name = "paper_id") val paperId: String?,
    @ColumnInfo(name = "occurred_at") val occurredAtEpochMillis: Long,
    @ColumnInfo(name = "duration_millis") val durationMillis: Long? = null,
    @ColumnInfo(name = "sync_state") val syncState: String = BehavioralEventSyncState.PENDING.value,
    @ColumnInfo(name = "sync_attempt_count") val syncAttemptCount: Int = 0,
    @ColumnInfo(name = "last_sync_attempt_at") val lastSyncAttemptAtEpochMillis: Long? = null,
    @ColumnInfo(name = "last_sync_error") val lastSyncError: String? = null,
)

enum class BehavioralEventSyncState(
    val value: String,
) {
    PENDING("pending"),
    IN_FLIGHT("in_flight"),
    SYNCED("synced"),
}
