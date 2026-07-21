package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.mneme.app.data.local.entity.PaperEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface PaperDao {
    @Query("SELECT * FROM papers ORDER BY updated_at DESC")
    fun observeAll(): Flow<List<PaperEntity>>

    @Query("SELECT * FROM papers WHERE id = :id")
    suspend fun getById(id: String): PaperEntity?

    @Query("SELECT * FROM papers ORDER BY updated_at DESC")
    suspend fun getAll(): List<PaperEntity>

    @Upsert
    suspend fun upsertAll(papers: List<PaperEntity>)

    @Query("UPDATE papers SET last_opened_at = :openedAtEpochMillis WHERE id = :id")
    suspend fun markOpened(
        id: String,
        openedAtEpochMillis: Long,
    )

    @Query(
        "DELETE FROM papers " +
            "WHERE updated_at < :recentPaperCutoffEpochMillis " +
            "AND (last_opened_at = 0 OR last_opened_at < :openedPaperCutoffEpochMillis)",
    )
    suspend fun deleteExpired(
        recentPaperCutoffEpochMillis: Long,
        openedPaperCutoffEpochMillis: Long,
    ): Int

    @Query("DELETE FROM papers")
    suspend fun clear()
}
