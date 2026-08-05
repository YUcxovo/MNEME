package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.mneme.app.data.local.SavedPaperProjection
import com.mneme.app.data.local.entity.PaperEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface PaperDao {
    @Query("SELECT * FROM papers ORDER BY updated_at DESC")
    fun observeAll(): Flow<List<PaperEntity>>

    @Query(
        "SELECT papers.*, MAX(behavioral_events.occurred_at) AS saved_at_epoch_millis " +
            "FROM papers INNER JOIN behavioral_events " +
            "ON behavioral_events.paper_id = papers.id " +
            "WHERE behavioral_events.event_type = :eventType " +
            "GROUP BY papers.id ORDER BY saved_at_epoch_millis DESC, papers.id ASC",
    )
    fun observeSavedPapers(eventType: String): Flow<List<SavedPaperProjection>>

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
            "AND (last_opened_at = 0 OR last_opened_at < :openedPaperCutoffEpochMillis) " +
            "AND id NOT IN (" +
            "SELECT paper_id FROM behavioral_events " +
            "WHERE event_type = 'paper_saved' AND paper_id IS NOT NULL" +
            ")",
    )
    suspend fun deleteExpired(
        recentPaperCutoffEpochMillis: Long,
        openedPaperCutoffEpochMillis: Long,
    ): Int

    @Query("DELETE FROM papers")
    suspend fun clear()
}
