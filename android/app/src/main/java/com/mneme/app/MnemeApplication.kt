package com.mneme.app

import android.app.Application
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.ContentUnavailableException
import com.mneme.app.data.repository.ControlledFixtureDataRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.QaUiModel

class MnemeApplication : Application() {
    val container: MnemeApplicationContainer by lazy {
        MnemeApplicationContainer(this)
    }

    override fun onCreate() {
        super.onCreate()
        com.mneme.app.sync.BehavioralEventSyncScheduler
            .schedule(androidx.work.WorkManager.getInstance(this))
    }
}

class MnemeApplicationContainer(
    application: Application,
) {
    private val database by lazy { MnemeDatabase.create(application) }

    private val remote: com.mneme.app.data.network.MnemeRemoteDataSource? by lazy {
        if (BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            null
        } else {
            runCatching {
                MnemeApiClient.create(
                    BuildConfig.MNEME_API_BASE_URL,
                    BuildConfig.MNEME_DEMO_TOKEN,
                )
            }.getOrNull()
        }
    }

    val behavioralEventSynchronizer: com.mneme.app.sync.BehavioralEventSynchronizer? by lazy {
        remote?.let {
            com.mneme.app.sync.BehavioralEventSynchronizer(
                com.mneme.app.data.local.BehavioralEventRepository(
                    database.behavioralEventDao(),
                ),
                it,
            )
        }
    }

    private val repository: SkeletalDataRepository by lazy {
        if (BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            ControlledFixtureDataRepository()
        } else {
            runCatching {
                val remote = requireNotNull(remote)
                com.mneme.app.data.repository.NetworkSkeletalDataRepository(
                    remote = remote,
                    cache = RoomSkeletalCache(database, MnemeApiClient.json),
                )
            }.getOrElse { error ->
                ConfigurationErrorRepository(
                    message = error.message ?: "The Android backend configuration is invalid.",
                )
            }
        }
    }

    val viewModelFactory: MnemeViewModel.Factory by lazy {
        MnemeViewModel.Factory(repository)
    }
}

private class ConfigurationErrorRepository(
    message: String,
) : SkeletalDataRepository {
    private val error = ContentUnavailableException(message)

    override val requiresSeedOnboarding: Boolean = false

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel = throw error

    override suspend fun loadBriefing(): BriefingUiModel = throw error

    override suspend fun loadPaper(paperId: String): PaperContentResult = throw error

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult = throw error

    override suspend fun askQuestion(
        paperId: String,
        question: String,
    ): QaUiModel = throw error
}
