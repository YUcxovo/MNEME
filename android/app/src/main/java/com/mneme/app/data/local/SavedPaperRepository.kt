package com.mneme.app.data.local

import androidx.room.ColumnInfo
import androidx.room.Embedded
import com.mneme.app.data.local.dao.PaperDao
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.PaperEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

data class SavedPaper(
    val id: String,
    val title: String,
    val authors: List<String>,
    val category: String?,
    val abstractText: String,
    val savedAtEpochMillis: Long,
)

data class SavedPaperProjection(
    @Embedded val paper: PaperEntity,
    @ColumnInfo(name = "saved_at_epoch_millis") val savedAtEpochMillis: Long,
)

interface SavedPaperStore {
    fun observeSavedPapers(): Flow<List<SavedPaper>>
}

object EmptySavedPaperStore : SavedPaperStore {
    override fun observeSavedPapers(): Flow<List<SavedPaper>> = flowOf(emptyList())
}

class RoomSavedPaperStore(
    private val paperDao: PaperDao,
    private val json: Json,
) : SavedPaperStore {
    override fun observeSavedPapers(): Flow<List<SavedPaper>> =
        paperDao
            .observeSavedPapers(BehavioralEventType.PAPER_SAVED.wireValue)
            .map { rows ->
                rows.map { row -> row.paper.toSavedPaper(row.savedAtEpochMillis, json) }
            }
}

internal fun projectSavedPapers(
    events: List<BehavioralEventEntity>,
    papers: List<PaperEntity>,
    json: Json,
): List<SavedPaper> {
    val savedAtByPaper =
        events
            .asSequence()
            .filter { event -> event.eventType == BehavioralEventType.PAPER_SAVED.wireValue }
            .mapNotNull { event -> event.paperId?.let { paperId -> paperId to event.occurredAtEpochMillis } }
            .groupingBy(Pair<String, Long>::first)
            .fold(0L) { latest, (_, occurredAt) -> maxOf(latest, occurredAt) }
    val papersById = papers.associateBy(PaperEntity::id)
    return savedAtByPaper
        .entries
        .sortedWith(
            compareByDescending<Map.Entry<String, Long>> { it.value }
                .thenBy { it.key },
        ).mapNotNull { (paperId, savedAt) ->
            papersById[paperId]?.toSavedPaper(savedAt, json)
        }
}

private fun PaperEntity.toSavedPaper(
    savedAtEpochMillis: Long,
    json: Json,
): SavedPaper =
    SavedPaper(
        id = id,
        title = title,
        authors =
            runCatching { json.decodeFromString<List<String>>(authorsJson) }
                .getOrDefault(emptyList()),
        category = primaryCategory,
        abstractText = abstractText,
        savedAtEpochMillis = savedAtEpochMillis,
    )
