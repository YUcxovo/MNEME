package com.mneme.app.data.local.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "papers",
    indices = [Index(value = ["arxiv_id"], unique = true)],
)
data class PaperEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "arxiv_id") val arxivId: String,
    val title: String,
    @ColumnInfo(name = "authors_json") val authorsJson: String,
    @ColumnInfo(name = "abstract_text") val abstractText: String,
    @ColumnInfo(name = "primary_category") val primaryCategory: String?,
    @ColumnInfo(name = "pdf_url") val pdfUrl: String?,
    @ColumnInfo(name = "processing_status") val processingStatus: String,
    @ColumnInfo(name = "updated_at") val updatedAtEpochMillis: Long,
    @ColumnInfo(name = "last_synced_at") val lastSyncedAtEpochMillis: Long = 0,
    @ColumnInfo(name = "last_opened_at") val lastOpenedAtEpochMillis: Long = 0,
)
