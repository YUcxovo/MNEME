package com.mneme.app

import android.app.Application
import androidx.work.WorkManager
import com.mneme.app.data.behavior.BehavioralEventSyncCoordinator
import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.behavior.NoOpBehavioralEventTracker
import com.mneme.app.data.behavior.QueuedBehavioralEventTracker
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.ContentUnavailableException
import com.mneme.app.data.repository.ControlledFixtureDataRepository
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.sync.BehavioralEventSyncScheduler
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.QaUiModel

class MnemeApplication : Application() {
    val container: MnemeApplicationContainer by lazy {
        MnemeApplicationContainer(this)
    }

    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.MNEME_DEMO_TOKEN.isNotBlank()) {
            BehavioralEventSyncScheduler.enqueue(WorkManager.getInstance(this))
        }
    }
}

class MnemeApplicationContainer(
    application: Application,
) {
    private val liveComponents: Result<LiveComponents>? by lazy {
        if (BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            null
        } else {
            runCatching {
                val database = MnemeDatabase.create(application)
                val remote =
                    MnemeApiClient.create(
                        baseUrl = BuildConfig.MNEME_API_BASE_URL,
                        demoToken = BuildConfig.MNEME_DEMO_TOKEN,
                    )
                val eventStore = BehavioralEventRepository(database.behavioralEventDao())
                val eventSyncCoordinator =
                    BehavioralEventSyncCoordinator(
                        store = eventStore,
                        remote = remote,
                    )
                LiveComponents(
                    repository =
                        NetworkSkeletalDataRepository(
                            remote = remote,
                            cache = RoomSkeletalCache(database, MnemeApiClient.json),
                        ),
                    eventTracker =
                        QueuedBehavioralEventTracker(
                            store = eventStore,
                            scheduleSync = {
                                BehavioralEventSyncScheduler.enqueue(
                                    WorkManager.getInstance(application),
                                )
                            },
                        ),
                    eventSyncCoordinator = eventSyncCoordinator,
                )
            }
        }
    }

    private val repository: SkeletalDataRepository by lazy {
        when (val live = liveComponents) {
            null -> ControlledFixtureDataRepository()
            else ->
                live.fold(
                    onSuccess = LiveComponents::repository,
                    onFailure = { error ->
                        ConfigurationErrorRepository(
                            message = error.message ?: "The Android backend configuration is invalid.",
                        )
                    },
                )
        }
    }

    private val eventTracker: BehavioralEventTracker by lazy {
        when (val live = liveComponents) {
            null -> NoOpBehavioralEventTracker
            else -> live.fold(LiveComponents::eventTracker) { NoOpBehavioralEventTracker }
        }
    }

    val behavioralEventSyncCoordinator: BehavioralEventSyncCoordinator?
        get() = liveComponents?.getOrNull()?.eventSyncCoordinator

    val viewModelFactory: MnemeViewModel.Factory by lazy {
        MnemeViewModel.Factory(repository, eventTracker)
    }
}

private data class LiveComponents(
    val repository: SkeletalDataRepository,
    val eventTracker: BehavioralEventTracker,
    val eventSyncCoordinator: BehavioralEventSyncCoordinator,
)

private class ConfigurationErrorRepository(
    message: String,
) : SkeletalDataRepository {
    private val error = ContentUnavailableException(message)

    override suspend fun restoreBriefing(): BriefingUiModel = throw error

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel = throw error

    override suspend fun loadBriefing(): BriefingUiModel = throw error

    override suspend fun updateInterests(topics: List<String>): BriefingUiModel = throw error

    override suspend fun loadPaper(paperId: String): PaperContentResult = throw error

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult = throw error

    override suspend fun askQuestion(
        paperId: String,
        question: String,
    ): QaUiModel = throw error

    override suspend fun loadGraph(paperId: String): GraphUiModel = throw error
}
