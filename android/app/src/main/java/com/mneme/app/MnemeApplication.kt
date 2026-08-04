package com.mneme.app

import android.app.Application
import android.content.Context
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
import com.mneme.app.notifications.DigestNotifier
import com.mneme.app.sync.BehavioralEventSyncScheduler
import com.mneme.app.sync.DigestNotificationState
import com.mneme.app.sync.DigestRefreshCoordinator
import com.mneme.app.sync.DigestSyncScheduler
import com.mneme.app.sync.LiveDigestBriefingRefresher
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
            DigestSyncScheduler.schedule(WorkManager.getInstance(this))
            BehavioralEventSyncScheduler.enqueue(WorkManager.getInstance(this))
        }
    }
}

class MnemeApplicationContainer(
    application: Application,
) {
    private val liveDatabase: Result<MnemeDatabase> by lazy {
        runCatching { MnemeDatabase.create(application) }
    }

    private val controlledFixtureDatabase: Result<MnemeDatabase> by lazy {
        runCatching { MnemeDatabase.createControlledFixture(application) }
    }

    private val liveComponents: Result<LiveComponents>? by lazy {
        if (BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            null
        } else {
            runCatching {
                val appDatabase = liveDatabase.getOrThrow()
                val remote =
                    MnemeApiClient.create(
                        baseUrl = BuildConfig.MNEME_API_BASE_URL,
                        demoToken = BuildConfig.MNEME_DEMO_TOKEN,
                    )
                val eventStore = BehavioralEventRepository(appDatabase.behavioralEventDao())
                val cache = RoomSkeletalCache(appDatabase, MnemeApiClient.json)
                val eventSyncCoordinator =
                    BehavioralEventSyncCoordinator(
                        store = eventStore,
                        remote = remote,
                    )
                LiveComponents(
                    repository =
                        NetworkSkeletalDataRepository(
                            remote = remote,
                            cache = cache,
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
                    digestRefreshCoordinator =
                        DigestRefreshCoordinator(
                            refresher = LiveDigestBriefingRefresher(remote, cache),
                            notificationState = SharedPreferencesDigestNotificationState(application),
                            notifier = DigestNotifier(application),
                            notificationThreshold = BuildConfig.MNEME_DIGEST_NOTIFICATION_THRESHOLD,
                        ),
                )
            }
        }
    }

    private val repository: SkeletalDataRepository by lazy {
        when (val live = liveComponents) {
            null ->
                if (BuildConfig.MNEME_ALLOW_CONTROLLED_FIXTURE) {
                    ControlledFixtureDataRepository()
                } else {
                    ConfigurationErrorRepository(
                        message = "The Mneme backend token is required for this build.",
                    )
                }
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
            null ->
                if (!BuildConfig.MNEME_ALLOW_CONTROLLED_FIXTURE) {
                    NoOpBehavioralEventTracker
                } else {
                    controlledFixtureDatabase.fold(
                        onSuccess = { controlledDatabase ->
                            QueuedBehavioralEventTracker(
                                store =
                                    BehavioralEventRepository(
                                        controlledDatabase.behavioralEventDao(),
                                    ),
                                scheduleSync = {},
                            )
                        },
                        onFailure = { NoOpBehavioralEventTracker },
                    )
                }
            else -> live.fold(LiveComponents::eventTracker) { NoOpBehavioralEventTracker }
        }
    }

    val behavioralEventSyncCoordinator: BehavioralEventSyncCoordinator?
        get() = liveComponents?.getOrNull()?.eventSyncCoordinator

    val digestRefreshCoordinator: DigestRefreshCoordinator?
        get() = liveComponents?.getOrNull()?.digestRefreshCoordinator

    val viewModelFactory: MnemeViewModel.Factory by lazy {
        MnemeViewModel.Factory(repository, eventTracker)
    }
}

private data class LiveComponents(
    val repository: SkeletalDataRepository,
    val eventTracker: BehavioralEventTracker,
    val eventSyncCoordinator: BehavioralEventSyncCoordinator,
    val digestRefreshCoordinator: DigestRefreshCoordinator,
)

private class SharedPreferencesDigestNotificationState(
    context: Context,
) : DigestNotificationState {
    private val preferences =
        context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    override fun lastNotifiedDigestId(): String? = preferences.getString(LAST_NOTIFIED_DIGEST_ID, null)

    override fun markNotified(digestId: String) {
        preferences.edit().putString(LAST_NOTIFIED_DIGEST_ID, digestId).apply()
    }

    private companion object {
        const val PREFERENCES_NAME = "digest_notifications"
        const val LAST_NOTIFIED_DIGEST_ID = "last_notified_digest_id"
    }
}

private class ConfigurationErrorRepository(
    message: String,
) : SkeletalDataRepository {
    private val error = ContentUnavailableException(message)

    override suspend fun restoreBriefing(): BriefingUiModel = throw error

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel = throw error

    override suspend fun loadBriefing(): BriefingUiModel = throw error

    override suspend fun loadBriefing(digestId: String): BriefingUiModel = throw error

    override suspend fun updateInterests(topics: List<String>): BriefingUiModel = throw error

    override suspend fun loadPaper(paperId: String): PaperContentResult = throw error

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult = throw error

    override suspend fun askQuestion(
        paperId: String,
        question: String,
        conversationId: String?,
    ): QaUiModel = throw error

    override suspend fun loadGraph(paperId: String): GraphUiModel = throw error
}
