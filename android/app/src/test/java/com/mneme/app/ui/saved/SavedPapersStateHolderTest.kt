package com.mneme.app.ui.saved

import com.mneme.app.data.local.SavedPaper
import com.mneme.app.data.local.SavedPaperStore
import com.mneme.app.ui.EventRecordingStatus
import com.mneme.app.ui.PaperEngagementUiState
import com.mneme.app.ui.SavedPapersUiState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class SavedPapersStateHolderTest {
    @Test
    fun roomFailureBecomesRetryableErrorAndRetryRestoresContent() =
        runBlocking {
            var observations = 0
            val store =
                object : SavedPaperStore {
                    override fun observeSavedPapers(): Flow<List<SavedPaper>> =
                        flow {
                            observations += 1
                            if (observations == 1) throw IOException("controlled Room failure")
                            emit(listOf(savedPaper()))
                        }
                }
            val holder = SavedPapersStateHolder(store, this)

            yield()
            assertEquals(
                SavedPapersUiState.Error(SAVED_PAPERS_UNAVAILABLE_MESSAGE),
                holder.state.value,
            )

            holder.retry()
            yield()

            val content = holder.state.value
            assertTrue(content is SavedPapersUiState.Content)
            content as SavedPapersUiState.Content
            assertEquals(listOf("paper-1"), content.papers.map { it.id })
            assertEquals(2, observations)
        }

    @Test
    fun emptyFlowDoesNotLeaveSavedPapersLoadingForever() =
        runBlocking {
            val store =
                object : SavedPaperStore {
                    override fun observeSavedPapers(): Flow<List<SavedPaper>> = flow { }
                }
            val holder = SavedPapersStateHolder(store, this)

            yield()

            assertEquals(
                SavedPapersUiState.Error(SAVED_PAPERS_UNAVAILABLE_MESSAGE),
                holder.state.value,
            )
        }

    @Test
    fun savedStoreErrorDoesNotLeaveSaveActionCheckingForever() {
        val engagement =
            PaperEngagementUiState(
                saveStatuses = mapOf("paper-1" to EventRecordingStatus.FAILED),
            )

        val savedState = SavedPapersUiState.Error(SAVED_PAPERS_UNAVAILABLE_MESSAGE)
        val status = savedState.saveStatus("paper-1", engagement)

        assertEquals(EventRecordingStatus.FAILED, status)
    }

    private fun savedPaper() =
        SavedPaper(
            id = "paper-1",
            title = "A cached paper",
            authors = listOf("Ada", "Grace"),
            category = "cs.CL",
            abstractText = "A real cached abstract.",
            savedAtEpochMillis = 10,
        )
}
