package com.mneme.app.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "cache_metadata")
data class CacheMetadataEntity(
    @PrimaryKey val id: String = SINGLETON_ID,
    @ColumnInfo(name = "last_successful_refresh_at")
    val lastSuccessfulRefreshAtEpochMillis: Long,
) {
    companion object {
        const val SINGLETON_ID = "digest-cache"
    }
}
