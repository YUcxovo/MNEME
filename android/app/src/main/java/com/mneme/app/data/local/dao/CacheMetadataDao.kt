package com.mneme.app.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.mneme.app.data.local.entity.CacheMetadataEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface CacheMetadataDao {
    @Query("SELECT * FROM cache_metadata WHERE id = :id")
    fun observe(id: String = CacheMetadataEntity.SINGLETON_ID): Flow<CacheMetadataEntity?>

    @Query("SELECT * FROM cache_metadata WHERE id = :id")
    suspend fun get(id: String = CacheMetadataEntity.SINGLETON_ID): CacheMetadataEntity?

    @Upsert
    suspend fun upsert(metadata: CacheMetadataEntity)
}
