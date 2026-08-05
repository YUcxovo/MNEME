package com.mneme.app.data.local

import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.local.entity.PaperEntity
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class SavedPaperRepositoryTest {
    @Test
    fun projectSavedPapers_deduplicatesAndOrdersDurableSaveEvents() {
        val papers = listOf(paper("paper-1", "First paper"), paper("paper-2", "Second paper"))
        val events =
            listOf(
                event("save-1", "paper-1", 100, BehavioralEventSyncState.SYNCED),
                event("save-2", "paper-2", 200, BehavioralEventSyncState.PENDING),
                event("save-3", "paper-1", 300, BehavioralEventSyncState.IN_FLIGHT),
                event("opened", "paper-2", 400, BehavioralEventSyncState.SYNCED, "paper_opened"),
            )

        val saved = projectSavedPapers(events, papers, Json)

        assertEquals(listOf("paper-1", "paper-2"), saved.map(SavedPaper::id))
        assertEquals(listOf(300L, 200L), saved.map(SavedPaper::savedAtEpochMillis))
        assertEquals(listOf("Ada", "Grace"), saved.first().authors)
    }

    @Test
    fun projectSavedPapers_omitsUnknownCachedPapers() {
        val events =
            listOf(
                event("known", "paper-1", 100, BehavioralEventSyncState.SYNCED),
                event("missing", "missing-paper", 200, BehavioralEventSyncState.SYNCED),
            )

        val saved = projectSavedPapers(events, listOf(paper("paper-1", "Known paper")), Json)

        assertEquals(listOf("paper-1"), saved.map(SavedPaper::id))
    }

    private fun paper(
        id: String,
        title: String,
    ) = PaperEntity(
        id = id,
        arxivId = "1706.03762",
        title = title,
        authorsJson = "[\"Ada\",\"Grace\"]",
        abstractText = "A real cached abstract.",
        primaryCategory = "cs.CL",
        pdfUrl = "https://arxiv.org/pdf/1706.03762",
        processingStatus = "ready",
        updatedAtEpochMillis = 1,
    )

    private fun event(
        id: String,
        paperId: String,
        occurredAt: Long,
        state: BehavioralEventSyncState,
        type: String = BehavioralEventType.PAPER_SAVED.wireValue,
    ) = BehavioralEventEntity(
        id = id,
        eventType = type,
        paperId = paperId,
        occurredAtEpochMillis = occurredAt,
        syncState = state.value,
    )
}
