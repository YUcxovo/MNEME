package com.mneme.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.behavior.NoOpBehavioralEventTracker
import com.mneme.app.data.local.EmptySavedPaperStore
import com.mneme.app.data.local.SavedPaperStore
import com.mneme.app.data.network.QUESTION_MAX_LENGTH
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.data.repository.toUserMessage
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.saved.SavedPapersStateHolder
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
    savedPaperStore: SavedPaperStore = EmptySavedPaperStore,
) : ViewModel() {
    val behavioralEvents = MnemeBehavioralEventRecorder(eventTracker, viewModelScope)

    private val savedPapersStateHolder = SavedPapersStateHolder(savedPaperStore, viewModelScope)
    val savedPapers: StateFlow<SavedPapersUiState> = savedPapersStateHolder.state
    val retrySavedPapers: () -> Unit = savedPapersStateHolder::retry

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

    private val _interestEditState =
        MutableStateFlow<InterestEditUiState>(InterestEditUiState.Idle)
    val interestEditState: StateFlow<InterestEditUiState> = _interestEditState.asStateFlow()

    private val qaConversations = mutableMapOf<String, List<QaUiModel>>()
    private var paperLoadJob: Job? = null
    private var qaLoadJob: Job? = null
    private var graphLoadJob: Job? = null
    private var briefingLoadJob: Job? = null
    private var activeBriefingDigestId: String? = null

    init {
        restoreBriefing()
    }

    fun initializeFromSeed(arxivReference: String) {
        require(arxivReference.isNotBlank()) { "An arXiv URL or identifier is required." }
        briefingLoadJob?.cancel()
        activeBriefingDigestId = null
        briefingLoadJob =
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
                } finally {
                    if (briefingLoadJob === coroutineContext[Job]) {
                        activeBriefingDigestId = null
                    }
                }
            }
    }

    fun editSeed() {
        briefingLoadJob?.cancel()
        activeBriefingDigestId = null
        _onboardingState.value = OnboardingUiState.AwaitingSeed
    }

    fun refreshBriefing(digestId: String? = null) {
        if (briefingLoadJob?.isActive == true && activeBriefingDigestId == digestId) return
        val displayedDigestId =
            (_homeState.value as? HomeUiState.Content)?.briefing?.digest?.id
        if (digestId != null && briefingLoadJob?.isActive != true && displayedDigestId == digestId) return
        briefingLoadJob?.cancel()
        activeBriefingDigestId = digestId
        briefingLoadJob =
            viewModelScope.launch {
                _homeState.value = HomeUiState.Loading
                try {
                    val briefing =
                        if (digestId == null) {
                            repository.loadBriefing()
                        } else {
                            require(digestId.isNotBlank()) { "A digest identifier is required." }
                            repository.loadBriefing(digestId)
                        }
                    _homeState.value = HomeUiState.Content(briefing)
                    if (digestId != null) _onboardingState.value = OnboardingUiState.Ready
                } catch (error: IOException) {
                    _homeState.value = HomeUiState.Error(error.toUserMessage())
                    if (digestId != null) _onboardingState.value = OnboardingUiState.Ready
                } catch (error: SerializationException) {
                    _homeState.value = HomeUiState.Error(error.toUserMessage())
                    if (digestId != null) _onboardingState.value = OnboardingUiState.Ready
                } finally {
                    if (briefingLoadJob === coroutineContext[Job]) {
                        activeBriefingDigestId = null
                    }
                }
            }
    }

    fun saveInterests(topics: List<String>) {
        briefingLoadJob?.cancel()
        activeBriefingDigestId = null
        briefingLoadJob =
            viewModelScope.launch {
                _interestEditState.value = InterestEditUiState.Saving
                try {
                    _homeState.value = HomeUiState.Content(repository.updateInterests(topics))
                    _interestEditState.value = InterestEditUiState.Saved
                } catch (error: CancellationException) {
                    _interestEditState.value = InterestEditUiState.Idle
                    throw error
                } catch (error: IllegalArgumentException) {
                    _interestEditState.value =
                        InterestEditUiState.Error(
                            error.message ?: "The research interests are invalid.",
                        )
                } catch (error: IOException) {
                    _interestEditState.value = InterestEditUiState.Error(error.toUserMessage())
                } catch (error: SerializationException) {
                    _interestEditState.value = InterestEditUiState.Error(error.toUserMessage())
                } finally {
                    if (briefingLoadJob === coroutineContext[Job]) {
                        activeBriefingDigestId = null
                    }
                }
            }
    }

    private fun restoreBriefing() {
        briefingLoadJob?.cancel()
        activeBriefingDigestId = null
        briefingLoadJob =
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
                } finally {
                    if (briefingLoadJob === coroutineContext[Job]) {
                        activeBriefingDigestId = null
                    }
                }
            }
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
        behavioralEvents.recordQuestionAsked(paperId)
        qaLoadJob?.cancel()
        val exchanges = qaConversations[paperId].orEmpty()
        val conversationId = exchanges.lastOrNull()?.conversationId
        qaLoadJob =
            viewModelScope.launch {
                _qaState.value = QaUiState.Loading(paperId, question, exchanges)
                try {
                    val answer =
                        repository.askQuestion(
                            paperId = paperId,
                            question = question,
                            conversationId = conversationId,
                        )
                    val updatedExchanges = exchanges + answer
                    qaConversations[paperId] = updatedExchanges
                    _qaState.value = QaUiState.Content(paperId, updatedExchanges)
                } catch (error: IOException) {
                    _qaState.value =
                        QaUiState.Error(
                            paperId = paperId,
                            question = question,
                            message = error.toUserMessage(),
                            exchanges = exchanges,
                        )
                } catch (error: SerializationException) {
                    _qaState.value =
                        QaUiState.Error(
                            paperId = paperId,
                            question = question,
                            message = error.toUserMessage(),
                            exchanges = exchanges,
                        )
                }
            }
    }

    fun openQa(paperId: String) {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        if (_qaState.value.paperIdOrNull() == paperId) {
            return
        }
        qaLoadJob?.cancel()
        _qaState.value = QaUiState.Content(paperId, qaConversations[paperId].orEmpty())
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

    class Factory(
        private val repository: SkeletalDataRepository,
        private val eventTracker: BehavioralEventTracker = NoOpBehavioralEventTracker,
        private val savedPaperStore: SavedPaperStore = EmptySavedPaperStore,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(MnemeViewModel::class.java)) {
                "Unsupported ViewModel class: ${modelClass.name}"
            }
            return MnemeViewModel(repository, eventTracker, savedPaperStore) as T
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
