package com.mneme.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.mneme.app.data.demo.SkeletalContentRepository
import com.mneme.app.ui.home.HomeUiState

internal fun MnemeViewModel.uiActions(): MnemeUiActions =
    MnemeUiActions(
        refreshBriefing = ::refreshBriefing,
        recordPaperImpressions = behavioralEvents::recordPaperImpressions,
        recordPaperOpened = behavioralEvents::recordPaperOpened,
        recordExternalPaperOpened = behavioralEvents::recordPaperOpenedOnce,
        requestPaper = { paperId -> loadPaper(paperId) },
        retryPaper = { paperId -> loadPaper(paperId, force = true) },
        openQa = ::openQa,
        requestQa = ::askQuestion,
        requestGraph = { paperId -> loadGraph(paperId) },
        retryGraph = { paperId -> loadGraph(paperId, force = true) },
        saveInterests = ::saveInterests,
        savePaper = behavioralEvents::savePaper,
        sharePaper = behavioralEvents::sharePaper,
    )

internal class FixtureMnemeState(
    private val repository: SkeletalContentRepository,
) {
    private var paperState by mutableStateOf<PaperDetailUiState>(PaperDetailUiState.Idle)
    private var qaState by mutableStateOf<QaUiState>(QaUiState.Idle)
    private var graphState by mutableStateOf<GraphUiState>(GraphUiState.Idle)
    private var interestEditState by mutableStateOf<InterestEditUiState>(InterestEditUiState.Idle)
    private var engagement by mutableStateOf(PaperEngagementUiState())
    private var briefing by mutableStateOf(repository.briefing())

    val snapshot: MnemeUiSnapshot
        get() =
            MnemeUiSnapshot(
                home = HomeUiState.Content(briefing),
                paper = paperState,
                qa = qaState,
                graph = graphState,
                interestEdit = interestEditState,
                engagement = engagement,
            )

    val actions =
        MnemeUiActions(
            refreshBriefing = {},
            recordPaperImpressions = {},
            recordPaperOpened = {},
            recordExternalPaperOpened = { _, _ -> false },
            requestPaper = ::loadPaper,
            retryPaper = ::loadPaper,
            openQa = ::openQa,
            requestQa = ::loadQa,
            requestGraph = ::loadGraph,
            retryGraph = ::loadGraph,
            saveInterests = { topics ->
                briefing = briefing.copy(interests = topics)
                interestEditState = InterestEditUiState.Saved
            },
            savePaper = { paperId ->
                engagement =
                    engagement.copy(
                        saveStatuses =
                            engagement.saveStatuses +
                                (paperId to EventRecordingStatus.RECORDED),
                    )
            },
            sharePaper = { paperId ->
                engagement =
                    engagement.copy(
                        shareStatuses =
                            engagement.shareStatuses +
                                (paperId to EventRecordingStatus.RECORDED),
                    )
            },
        )

    private fun loadPaper(paperId: String) {
        paperState =
            repository.paper(paperId)?.let(PaperDetailUiState::Content)
                ?: PaperDetailUiState.Error(paperId, "The selected paper is not available.")
    }

    private fun openQa(paperId: String) {
        if (qaState.paperIdOrNull() != paperId) {
            qaState = QaUiState.Content(paperId, emptyList())
        }
    }

    private fun loadQa(
        paperId: String,
        question: String,
    ) {
        val exchanges = qaState.completedExchanges()
        qaState =
            repository.qa(paperId, question)?.let { answer ->
                QaUiState.Content(paperId, exchanges + answer)
            } ?: QaUiState.Error(
                paperId = paperId,
                question = question,
                message = "A paper-specific answer is not available.",
                exchanges = exchanges,
            )
    }

    private fun loadGraph(paperId: String) {
        graphState =
            repository.graph(paperId)?.let(GraphUiState::Content)
                ?: GraphUiState.Error(paperId, "A citation graph is not available for this paper.")
    }
}
