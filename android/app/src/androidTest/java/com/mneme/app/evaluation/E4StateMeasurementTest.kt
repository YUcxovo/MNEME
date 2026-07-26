@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.OnboardingUiState
import com.mneme.app.ui.PaperDetailUiState
import com.mneme.app.ui.ScenarioRepository
import com.mneme.app.ui.e4Briefing
import com.mneme.app.ui.e4Processing
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.model.ContentOrigin
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class E4StateMeasurementTest {
    @Test
    fun recordControlledStateResolutionAndPollingLatency() {
        E4MeasurementFiles.resetCsv(STATE_FILE, STATE_HEADER)
        var failedSamples = 0

        val scenarios =
            listOf(
                StateScenario("live_seed") { liveSeedSample() },
                StateScenario("cached_warm_start") { cachedWarmStartSample() },
                StateScenario("cached_offline_disclosure") { cachedOfflineSample() },
                StateScenario("cached_server_failure_disclosure") { cachedServerFailureSample() },
                StateScenario("invalid_cache_error") { invalidCacheSample() },
            )
        scenarios.forEach { scenario ->
            repeat(WARMUP_ITERATIONS + STATE_ITERATIONS) { index ->
                val measured = index >= WARMUP_ITERATIONS
                val sample = runCatching(scenario.run).getOrElse { error -> failedSample(error) }
                if (measured) {
                    if (!sample.success) {
                        failedSamples += 1
                    }
                    recordStateSample(
                        scenario = scenario.name,
                        iteration = index - WARMUP_ITERATIONS + 1,
                        sample = sample,
                    )
                }
            }
        }

        repeat(POLL_WARMUP_ITERATIONS + POLL_ITERATIONS) { index ->
            val measured = index >= POLL_WARMUP_ITERATIONS
            val sample = runCatching(::jobPollingSample).getOrElse { error -> failedSample(error) }
            if (measured) {
                if (!sample.success) {
                    failedSamples += 1
                }
                recordStateSample(
                    scenario = "three_stage_job_polling",
                    iteration = index - POLL_WARMUP_ITERATIONS + 1,
                    sample = sample,
                )
            }
        }

        assertEquals("Every measured controlled state sample must complete.", 0, failedSamples)
    }

    private fun liveSeedSample(): StateSample {
        val repository =
            ScenarioRepository(
                restoredBriefing = null,
                seedBriefing =
                    e4Briefing(
                        origin = ContentOrigin.LIVE_BACKEND,
                        message = "Seed preparation completed.",
                        fivePapers = true,
                    ),
            )
        val viewModel = createViewModel(repository)
        check(waitUntil { viewModel.onboardingState.value is OnboardingUiState.AwaitingSeed })

        val startedAt = SystemClock.elapsedRealtimeNanos()
        runOnMain {
            viewModel.initializeFromSeed("https://arxiv.org/abs/1706.03762")
        }
        val success =
            waitUntil {
                val content = viewModel.homeState.value as? HomeUiState.Content
                content?.briefing?.papers?.size == 5 &&
                    content.briefing.disclosure.origin == ContentOrigin.LIVE_BACKEND
            }
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "five_paper_live_content" else "timeout",
            origin = originOf(viewModel.homeState.value),
        )
    }

    private fun cachedWarmStartSample(): StateSample {
        val cached =
            e4Briefing(
                origin = ContentOrigin.CACHED_BACKEND,
                message = "Restored from this device.",
            )
        val startedAt = SystemClock.elapsedRealtimeNanos()
        val viewModel =
            createViewModel(
                ScenarioRepository(
                    restoredBriefing = cached,
                    refreshedBriefing = cached,
                ),
            )
        val success =
            waitUntil {
                (viewModel.homeState.value as? HomeUiState.Content)
                    ?.briefing
                    ?.disclosure
                    ?.origin == ContentOrigin.CACHED_BACKEND
            }
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "cached_content_visible" else "timeout",
            origin = originOf(viewModel.homeState.value),
        )
    }

    private fun cachedOfflineSample(): StateSample {
        val cached =
            e4Briefing(
                origin = ContentOrigin.CACHED_BACKEND,
                message = "Network unavailable; cached briefing retained.",
            )
        val startedAt = SystemClock.elapsedRealtimeNanos()
        val viewModel =
            createViewModel(
                ScenarioRepository(
                    restoredBriefing = cached,
                    refreshedBriefing = cached,
                ),
            )
        val success =
            waitUntil {
                val content = viewModel.homeState.value as? HomeUiState.Content
                content?.briefing?.disclosure?.origin == ContentOrigin.CACHED_BACKEND &&
                    content.briefing.disclosure.message
                        .contains("Network unavailable")
            }
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "offline_cache_retained" else "timeout",
            origin = originOf(viewModel.homeState.value),
        )
    }

    private fun cachedServerFailureSample(): StateSample {
        val restored =
            e4Briefing(
                origin = ContentOrigin.CACHED_BACKEND,
                message = "Restored while checking for updates.",
            )
        val failedRefresh =
            e4Briefing(
                origin = ContentOrigin.CACHED_BACKEND,
                message = "The server refresh failed; the last successful briefing remains available.",
            )
        val startedAt = SystemClock.elapsedRealtimeNanos()
        val viewModel =
            createViewModel(
                ScenarioRepository(
                    restoredBriefing = restored,
                    refreshedBriefing = failedRefresh,
                ),
            )
        val success =
            waitUntil {
                val content = viewModel.homeState.value as? HomeUiState.Content
                content
                    ?.briefing
                    ?.disclosure
                    ?.message
                    ?.contains("server refresh failed") == true
            }
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "server_failure_disclosed_with_cache" else "timeout",
            origin = originOf(viewModel.homeState.value),
        )
    }

    private fun invalidCacheSample(): StateSample {
        val startedAt = SystemClock.elapsedRealtimeNanos()
        val viewModel =
            createViewModel(
                ScenarioRepository(
                    invalidStoredBriefing = true,
                ),
            )
        val success = waitUntil { viewModel.homeState.value is HomeUiState.Error }
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "contract_error_visible" else "timeout",
            origin = originOf(viewModel.homeState.value),
        )
    }

    private fun jobPollingSample(): StateSample {
        val readyPaper =
            requireNotNull(
                SeededSkeletalContentRepository.paper(SeededSkeletalContentRepository.PAPER_ID),
            )
        val repository =
            ScenarioRepository(
                restoredBriefing =
                    e4Briefing(
                        origin = ContentOrigin.LIVE_BACKEND,
                        message = "Live briefing.",
                    ),
                refreshedBriefing =
                    e4Briefing(
                        origin = ContentOrigin.LIVE_BACKEND,
                        message = "Live briefing.",
                    ),
                paperResults =
                    listOf(
                        e4Processing("download_pdf"),
                        e4Processing("parse_pdf"),
                        e4Processing("summarize_paper"),
                        PaperContentResult.Ready(readyPaper),
                    ),
            )
        val viewModel = createViewModel(repository)
        check(waitUntil { viewModel.homeState.value is HomeUiState.Content })

        val startedAt = SystemClock.elapsedRealtimeNanos()
        runOnMain {
            viewModel.loadPaper(SeededSkeletalContentRepository.PAPER_ID)
        }
        val success =
            waitUntil(timeoutMillis = POLL_TIMEOUT_MILLIS) {
                viewModel.paperState.value is PaperDetailUiState.Content
            } &&
                repository.refreshedJobIds.size == EXPECTED_POLL_COUNT
        return StateSample(
            durationMillis = elapsedMillis(startedAt),
            success = success,
            outcome = if (success) "paper_ready" else "timeout_or_poll_mismatch",
            origin = "",
            expectedPolls = EXPECTED_POLL_COUNT,
            observedPolls = repository.refreshedJobIds.size,
        )
    }

    private fun createViewModel(repository: ScenarioRepository): MnemeViewModel {
        lateinit var viewModel: MnemeViewModel
        runOnMain {
            viewModel = MnemeViewModel(repository)
        }
        return viewModel
    }

    private fun recordStateSample(
        scenario: String,
        iteration: Int,
        sample: StateSample,
    ) {
        E4MeasurementFiles.appendCsv(
            STATE_FILE,
            listOf(
                "state",
                scenario,
                iteration,
                sample.durationMillis,
                sample.success,
                sample.outcome,
                sample.origin,
                sample.expectedPolls,
                sample.observedPolls,
            ),
        )
    }

    private fun waitUntil(
        timeoutMillis: Long = STATE_TIMEOUT_MILLIS,
        predicate: () -> Boolean,
    ): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMillis
        while (SystemClock.elapsedRealtime() < deadline) {
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            if (predicate()) {
                return true
            }
            Thread.sleep(POLL_INTERVAL_MILLIS)
        }
        return predicate()
    }

    private fun runOnMain(block: () -> Unit) {
        InstrumentationRegistry.getInstrumentation().runOnMainSync(block)
    }

    private fun originOf(state: HomeUiState): String =
        (state as? HomeUiState.Content)
            ?.briefing
            ?.disclosure
            ?.origin
            ?.name
            .orEmpty()

    private fun elapsedMillis(startedAtNanos: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAtNanos) / NANOS_PER_MILLISECOND

    private fun failedSample(error: Throwable): StateSample =
        StateSample(
            durationMillis = 0.0,
            success = false,
            outcome = error::class.java.simpleName,
            origin = "",
        )

    private data class StateScenario(
        val name: String,
        val run: () -> StateSample,
    )

    private data class StateSample(
        val durationMillis: Double,
        val success: Boolean,
        val outcome: String,
        val origin: String,
        val expectedPolls: Int? = null,
        val observedPolls: Int? = null,
    )

    private companion object {
        const val STATE_FILE = "state_measurements.csv"
        const val WARMUP_ITERATIONS = 3
        const val STATE_ITERATIONS = 30
        const val POLL_WARMUP_ITERATIONS = 1
        const val POLL_ITERATIONS = 10
        const val EXPECTED_POLL_COUNT = 3
        const val STATE_TIMEOUT_MILLIS = 5_000L
        const val POLL_TIMEOUT_MILLIS = 6_000L
        const val POLL_INTERVAL_MILLIS = 2L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        val STATE_HEADER =
            listOf(
                "track",
                "scenario",
                "iteration",
                "duration_ms",
                "success",
                "outcome",
                "origin",
                "expected_polls",
                "observed_polls",
            )
    }
}
