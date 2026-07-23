package com.mneme.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.behavior.NoOpBehavioralEventTracker
import com.mneme.app.data.network.QUESTION_MAX_LENGTH
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.data.repository.toUserMessage
import com.mneme.app.ui.home.HomeUiState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.SerializationException
import java.io.IOException

class MnemeViewModel(
    private val repository: SkeletalDataRepository,
    private val eventTracker: BehavioralEventTracker = NoOpBehavioralEventTracker,
) : ViewModel() {
    private val _onboardingState =
        MutableStateFlow<OnboardingUiState>(OnboardingUiState.Checking)
    val onboardingState: StateFlow<OnboardingUiState> = _onboardingState.asStateFlow()

    private val _homeState = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val homeState: StateFlow<HomeUiState> = _homeState.asStateFlow()

    private val _paperState = MutableStateFlow<PaperDetailUiState>(PaperDetailUiState.Idle)
    val paperState: StateFlow<PaperDetailUiState> = _paperState.asStateFlow()

    private val _qaState = MutableStateFlow<QaUiState>(QaUiState.Idle)
    val qaState: StateFlow<QaUiState> = _qaState.asStateFlow()

    private val _graphState = MutableStateFlow<GraphUiState>(GraphUiState.Idle)
    val graphState: StateFlow<GraphUiState> = _graphState.asStateFlow()

    private var paperLoadJob: Job? = null
    private var qaLoadJob: Job? = null
    private var graphLoadJob: Job? = null

    init {
        restoreBriefing()
    }

    fun initializeFromSeed(arxivReference: String) {
        require(arxivReference.isNotBlank()) { "An arXiv URL or identifier is required." }
        viewModelScope.launch {
            val normalized = arxivReference.trim()
            _onboardingState.value = OnboardingUiState.Loading(normalized)
            _homeState.value = HomeUiState.Loading
            try {
                _homeState.value = HomeUiState.Content(repository.initializeFromSeed(normalized))
                _onboardingState.value = OnboardingUiState.Ready
            } catch (error: IOException) {
                _onboardingState.value = OnboardingUiState.Error(normalized, error.toUserMessage())
            } catch (error: SerializationException) {
                _onboardingState.value = OnboardingUiState.Error(normalized, error.toUserMessage())
            }
        }
    }

    fun editSeed() {
        _onboardingState.value = OnboardingUiState.AwaitingSeed
    }

    fun refreshBriefing() {
        viewModelScope.launch {
            _homeState.updateFrom(repository, showLoading = true)
        }
    }

    private fun restoreBriefing() {
        viewModelScope.launch {
            try {
                val restored = repository.restoreBriefing()
                if (restored == null) {
                    _onboardingState.value = OnboardingUiState.AwaitingSeed
                    return@launch
                }
                _homeState.value = HomeUiState.Content(restored)
                _onboardingState.value = OnboardingUiState.Ready
                _homeState.updateFrom(repository, showLoading = false)
            } catch (error: IOException) {
                _onboardingState.value = OnboardingUiState.Ready
                _homeState.value = HomeUiState.Error(error.toUserMessage())
            } catch (error: SerializationException) {
                _onboardingState.value = OnboardingUiState.Ready
                _homeState.value = HomeUiState.Error(error.toUserMessage())
            }
        }
    }

    fun recordPaperImpressions(paperIds: List<String>) {
        recordBehavior { eventTracker.recordPaperImpressions(paperIds) }
    }

    fun recordPaperOpened(paperId: String) {
        recordBehavior { eventTracker.recordPaperOpened(paperId) }
    }

    fun loadPaper(
        paperId: String,
        force: Boolean = false,
    ) {
        if (!force && _paperState.value.matches(paperId)) {
            return
        }
        paperLoadJob?.cancel()
        paperLoadJob =
            viewModelScope.launch {
                _paperState.value =
                    PaperDetailUiState.Loading(
                        paperId = paperId,
                        message = "Loading paper and summary...",
                    )
                try {
                    followPaperResult(repository.loadPaper(paperId))
                } catch (error: CancellationException) {
                    throw error
                } catch (error: IOException) {
                    _paperState.value = PaperDetailUiState.Error(paperId, error.toUserMessage())
                } catch (error: SerializationException) {
                    _paperState.value = PaperDetailUiState.Error(paperId, error.toUserMessage())
                }
            }
    }

    fun askQuestion(
        paperId: String,
        question: String,
    ) {
        require(question.isNotBlank()) { "Question must not be blank." }
        require(question.length <= QUESTION_MAX_LENGTH) {
            "Question must not exceed $QUESTION_MAX_LENGTH characters."
        }
        recordBehavior { eventTracker.recordQuestionAsked(paperId) }
        qaLoadJob?.cancel()
        qaLoadJob =
            viewModelScope.launch {
                _qaState.value = QaUiState.Loading(paperId, question)
                try {
                    _qaState.value = QaUiState.Content(repository.askQuestion(paperId, question))
                } catch (error: IOException) {
                    _qaState.value = QaUiState.Error(paperId, question, error.toUserMessage())
                } catch (error: SerializationException) {
                    _qaState.value = QaUiState.Error(paperId, question, error.toUserMessage())
                }
            }
    }

    fun loadGraph(
        paperId: String,
        force: Boolean = false,
    ) {
        if (!force && _graphState.value.matches(paperId)) {
            return
        }
        graphLoadJob?.cancel()
        graphLoadJob =
            viewModelScope.launch {
                _graphState.value = GraphUiState.Loading(paperId)
                try {
                    _graphState.value = GraphUiState.Content(repository.loadGraph(paperId))
                } catch (error: CancellationException) {
                    throw error
                } catch (error: IOException) {
                    _graphState.value = GraphUiState.Error(paperId, error.toUserMessage())
                } catch (error: SerializationException) {
                    _graphState.value = GraphUiState.Error(paperId, error.toUserMessage())
                }
            }
    }

    private suspend fun followPaperResult(initialResult: PaperContentResult) {
        var result = initialResult
        while (true) {
            when (val current = result) {
                is PaperContentResult.Ready -> {
                    _paperState.value = PaperDetailUiState.Content(current.paper)
                    return
                }
                is PaperContentResult.Processing -> {
                    _paperState.value =
                        PaperDetailUiState.Loading(
                            paperId = current.paperId,
                            message = current.stage.toProgressMessage(),
                        )
                    delay(JOB_POLL_INTERVAL_MILLIS)
                    result = repository.refreshPaper(current.paperId, current.jobId)
                }
            }
        }
    }

    private fun recordBehavior(block: suspend () -> Unit) {
        viewModelScope.launch {
            runCatching { block() }
        }
    }

    class Factory(
        private val repository: SkeletalDataRepository,
        private val eventTracker: BehavioralEventTracker = NoOpBehavioralEventTracker,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(MnemeViewModel::class.java)) {
                "Unsupported ViewModel class: ${modelClass.name}"
            }
            return MnemeViewModel(repository, eventTracker) as T
        }
    }

    companion object {
        const val JOB_POLL_INTERVAL_MILLIS = 1_000L
    }
}

private suspend fun MutableStateFlow<HomeUiState>.updateFrom(
    repository: SkeletalDataRepository,
    showLoading: Boolean,
) {
    if (showLoading) {
        value = HomeUiState.Loading
    }
    try {
        value = HomeUiState.Content(repository.loadBriefing())
    } catch (error: IOException) {
        value = HomeUiState.Error(error.toUserMessage())
    } catch (error: SerializationException) {
        value = HomeUiState.Error(error.toUserMessage())
    }
}

private fun PaperDetailUiState.matches(paperId: String): Boolean =
    when (this) {
        PaperDetailUiState.Idle -> false
        is PaperDetailUiState.Loading -> this.paperId == paperId
        is PaperDetailUiState.Content -> paper.paper.id == paperId
        is PaperDetailUiState.Error -> false
    }

private fun String.toProgressMessage(): String =
    when (this) {
        "download_pdf" -> "Downloading the source paper..."
        "parse_pdf" -> "Extracting the paper text..."
        "summarize_paper" -> "Generating the paper summary..."
        else -> "Preparing the paper summary..."
    }

private fun GraphUiState.matches(paperId: String): Boolean =
    when (this) {
        GraphUiState.Idle -> false
        is GraphUiState.Loading -> this.paperId == paperId
        is GraphUiState.Content -> graph.centerId == paperId
        is GraphUiState.Error -> false
    }
