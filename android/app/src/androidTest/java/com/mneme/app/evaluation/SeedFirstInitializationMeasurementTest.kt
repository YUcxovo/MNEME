@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.ui.MnemeApp
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.OnboardingUiState
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SeedFirstInitializationMeasurementTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun seedSubmission_measuresOneFreshInitializationUntilLiveFivePaperBriefingIsVisible() {
        val arguments = InstrumentationRegistry.getArguments()
        val input =
            MeasurementInput(
                trialId = arguments.getString(TRIAL_ARGUMENT).orEmpty(),
                seedArxivId = arguments.getString(SEED_ARGUMENT).orEmpty(),
                baseUrl = arguments.getString(BASE_URL_ARGUMENT).orEmpty(),
                token = arguments.getString(TOKEN_ARGUMENT).orEmpty(),
            )
        SeedFirstInitializationMeasurementFiles.reset()
        var stage = "arguments"
        var startedAtNanos: Long? = null
        var paperCount: Int? = null
        var paperIds = emptyList<String>()
        var contentOrigin: String? = null
        var database: MnemeDatabase? = null
        try {
            input.validate()
            val context = ApplicationProvider.getApplicationContext<Context>()
            database = MnemeDatabase.create(context)
            val repository =
                NetworkSkeletalDataRepository(
                    remote = MnemeApiClient.create(input.baseUrl, input.token),
                    cache = RoomSkeletalCache(database, MnemeApiClient.json),
                )
            val viewModel = MnemeViewModel(repository)
            composeRule.setContent {
                MnemeTheme {
                    MnemeApp(viewModel = viewModel)
                }
            }
            stage = "awaiting_seed"
            composeRule.waitUntil(UI_TIMEOUT_MILLIS) {
                viewModel.onboardingState.value is OnboardingUiState.AwaitingSeed
            }
            composeRule.onNodeWithTag("seed-paper-input").performTextInput(input.seedArxivId)
            stage = "seed_submission"
            startedAtNanos = SystemClock.elapsedRealtimeNanos()
            composeRule.onNodeWithTag("seed-paper-submit").performClick()
            stage = "live_briefing_state"
            composeRule.waitUntil(LIVE_TIMEOUT_MILLIS) {
                when (viewModel.onboardingState.value) {
                    OnboardingUiState.Ready,
                    is OnboardingUiState.Error,
                    -> true
                    else -> false
                }
            }
            check(viewModel.onboardingState.value is OnboardingUiState.Ready) {
                "Seed initialization did not reach the ready state."
            }
            val home = viewModel.homeState.value
            check(home is HomeUiState.Content) {
                "Seed initialization did not return briefing content."
            }
            paperCount = home.briefing.papers.size
            paperIds = home.briefing.papers.map { paper -> paper.id }
            contentOrigin = home.briefing.disclosure.origin.name
            stage = "visible_briefing"
            composeRule.onNodeWithTag("briefing-screen").assertIsDisplayed()
            composeRule.onNodeWithTag("content-source-notice").assertIsDisplayed()
            composeRule
                .onNodeWithTag("briefing-content-5-live-backend")
                .assertIsDisplayed()
            val finishedAtNanos = SystemClock.elapsedRealtimeNanos()
            stage = "success_criteria"
            check(paperCount == EXPECTED_PAPER_COUNT) {
                "The live briefing did not contain exactly five papers."
            }
            check(paperIds.distinct().size == EXPECTED_PAPER_COUNT) {
                "The live briefing paper identifiers were not unique."
            }
            check(contentOrigin == ContentOrigin.LIVE_BACKEND.name) {
                "The visible briefing was not labelled as live backend content."
            }
            SeedFirstInitializationMeasurementFiles.write(
                input = input,
                durationMillis = elapsedMillis(requireNotNull(startedAtNanos), finishedAtNanos),
                success = true,
                outcome = "live_five_paper_briefing_visible",
                paperCount = paperCount,
                paperIds = paperIds,
                contentOrigin = contentOrigin,
            )
        } catch (error: Throwable) {
            val finishedAtNanos = SystemClock.elapsedRealtimeNanos()
            SeedFirstInitializationMeasurementFiles.write(
                input = input,
                durationMillis =
                    startedAtNanos?.let { started ->
                        elapsedMillis(started, finishedAtNanos)
                    },
                success = false,
                outcome = "failed_${stage}_${error.javaClass.simpleName}",
                paperCount = paperCount,
                paperIds = paperIds,
                contentOrigin = contentOrigin,
            )
            throw error
        } finally {
            database?.close()
        }
    }

    private fun elapsedMillis(
        startedAtNanos: Long,
        finishedAtNanos: Long,
    ): Double = (finishedAtNanos - startedAtNanos) / NANOS_PER_MILLISECOND

    internal data class MeasurementInput(
        val trialId: String,
        val seedArxivId: String,
        val baseUrl: String,
        val token: String,
    ) {
        fun validate() {
            require(TRIAL_PATTERN.matches(trialId)) { "The trial argument is invalid." }
            require(seedArxivId in FIXED_SEEDS) { "The seed is not in the fixed evaluation set." }
            require(baseUrl.startsWith("http://10.0.2.2:")) {
                "The evaluation backend must use the emulator loopback gateway."
            }
            require(baseUrl.endsWith("/v1/")) { "The backend URL must end in /v1/." }
            require(token.isNotBlank()) { "The live evaluation token is required." }
        }
    }

    private companion object {
        const val TRIAL_ARGUMENT = "seedFirstTrial"
        const val SEED_ARGUMENT = "seedFirstSeed"
        const val BASE_URL_ARGUMENT = "seedFirstBaseUrl"
        const val TOKEN_ARGUMENT = "seedFirstToken"
        const val EXPECTED_PAPER_COUNT = 5
        const val UI_TIMEOUT_MILLIS = 30_000L
        const val LIVE_TIMEOUT_MILLIS = 15 * 60 * 1_000L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        val TRIAL_PATTERN = Regex("trial_0[1-3]")
        val FIXED_SEEDS = setOf("1706.03762", "2010.11929", "2106.09685")
    }
}
