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
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.QaUiModel

class MnemeApplication : Application() {
    val container: MnemeApplicationContainer by lazy {
        MnemeApplicationContainer(this)
    }
}

class MnemeApplicationContainer(
    application: Application,
) {
    private val repository: SkeletalDataRepository by lazy {
        if (BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            ControlledFixtureDataRepository()
        } else {
            runCatching {
                val database = MnemeDatabase.create(application)
                val remote =
                    MnemeApiClient.create(
                        baseUrl = BuildConfig.MNEME_API_BASE_URL,
                        demoToken = BuildConfig.MNEME_DEMO_TOKEN,
                    )
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

    override suspend fun loadGraph(paperId: String): GraphUiModel = throw error
}
