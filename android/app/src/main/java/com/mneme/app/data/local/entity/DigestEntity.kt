package com.mneme.app.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "digests")
data class DigestEntity(
    @PrimaryKey val id: String,
    val title: String,
    val summary: String,
    @ColumnInfo(name = "digest_type") val digestType: String,
    @ColumnInfo(name = "generated_at") val generatedAtEpochMillis: Long,
    @ColumnInfo(name = "last_synced_at") val lastSyncedAtEpochMillis: Long = 0,
)
