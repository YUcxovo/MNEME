package com.mneme.app.ui.saved

import com.mneme.app.data.local.SavedPaper
import com.mneme.app.data.local.SavedPaperStore
import com.mneme.app.ui.EventRecordingStatus
import com.mneme.app.ui.PaperEngagementUiState
import com.mneme.app.ui.SavedPapersUiState
import com.mneme.app.ui.model.PaperUiModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

internal class SavedPapersStateHolder(
    private val store: SavedPaperStore,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow<SavedPapersUiState>(SavedPapersUiState.Loading)
    val state: StateFlow<SavedPapersUiState> = _state.asStateFlow()

    private var observationJob: Job? = null

    init {
        retry()
    }

    fun retry() {
        observationJob?.cancel()
        _state.value = SavedPapersUiState.Loading
        observationJob =
            scope.launch {
                try {
                    var receivedSnapshot = false
                    store.observeSavedPapers().collect { papers ->
                        receivedSnapshot = true
                        _state.value = SavedPapersUiState.Content(papers.map(SavedPaper::toUiModel))
                    }
                    if (!receivedSnapshot) {
                        _state.value = SavedPapersUiState.Error(SAVED_PAPERS_UNAVAILABLE_MESSAGE)
                    }
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    _state.value = SavedPapersUiState.Error(SAVED_PAPERS_UNAVAILABLE_MESSAGE)
                }
            }
    }
}

internal fun SavedPapersUiState.saveStatus(
    paperId: String,
    engagement: PaperEngagementUiState,
): EventRecordingStatus =
    when (this) {
        SavedPapersUiState.Loading -> EventRecordingStatus.CHECKING
        is SavedPapersUiState.Content ->
            engagement.saveStatus(
                paperId = paperId,
                persistedSavedPaperIds = papers.mapTo(mutableSetOf()) { it.id },
            )
        is SavedPapersUiState.Error -> engagement.saveStatus(paperId)
    }

private fun SavedPaper.toUiModel(): PaperUiModel =
    PaperUiModel(
        id = id,
        title = title,
        authors = authors.joinToString(", "),
        category = category ?: "arXiv",
        summary = abstractText,
    )

internal const val SAVED_PAPERS_UNAVAILABLE_MESSAGE =
    "Saved papers are temporarily unavailable. Try loading them again."
