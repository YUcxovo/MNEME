package com.mneme.app.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "user_preferences")
data class UserPrefsEntity(
    @PrimaryKey @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "topics_json") val topicsJson: String,
    @ColumnInfo(name = "keywords_json") val keywordsJson: String,
    @ColumnInfo(name = "notifications_enabled") val notificationsEnabled: Boolean,
    @ColumnInfo(name = "updated_at") val updatedAtEpochMillis: Long,
    @ColumnInfo(name = "last_synced_at") val lastSyncedAtEpochMillis: Long = 0,
)
