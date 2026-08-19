package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.mneme.app.data.local.entity.DigestEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface DigestDao {
    @Query("SELECT * FROM digests ORDER BY generated_at DESC")
    fun observeAll(): Flow<List<DigestEntity>>

    @Query("SELECT * FROM digests WHERE id = :id")
    suspend fun getById(id: String): DigestEntity?

    @Query("SELECT * FROM digests ORDER BY generated_at DESC LIMIT 1")
    suspend fun getLatest(): DigestEntity?

    @Upsert
    suspend fun upsertAll(digests: List<DigestEntity>)

    @Query("DELETE FROM digests WHERE generated_at < :cutoffEpochMillis")
    suspend fun deleteOlderThan(cutoffEpochMillis: Long): Int

    @Query("DELETE FROM digests")
    suspend fun clear()
}
