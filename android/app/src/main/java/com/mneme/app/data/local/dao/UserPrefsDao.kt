package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.mneme.app.data.local.entity.UserPrefsEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface UserPrefsDao {
    @Query("SELECT * FROM user_preferences WHERE user_id = :userId")
    fun observe(userId: String): Flow<UserPrefsEntity?>

    @Query("SELECT * FROM user_preferences WHERE user_id = :userId")
    suspend fun get(userId: String): UserPrefsEntity?

    @Upsert
    suspend fun upsert(preferences: UserPrefsEntity)

    @Query("DELETE FROM user_preferences WHERE user_id = :userId")
    suspend fun delete(userId: String)
}
