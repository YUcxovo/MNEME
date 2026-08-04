@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class E4StateMatrixTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun s1_emptyStorageAndValidSeed_reachesLiveFivePaperBriefing() {
        val repository =
            ScenarioRepository(
                restoredBriefing = null,
                seedBriefing =
                    e4Briefing(
                        ContentOrigin.LIVE_BACKEND,
                        "Seed preparation completed.",
                        fivePapers = true,
                    ),
            )
        val viewModel = showApp(repository)

        composeRule.onNodeWithTag("seed-onboarding-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("seed-paper-input").performTextInput("https://arxiv.org/abs/1706.03762")
        composeRule.onNodeWithTag("seed-paper-submit").performClick()
        waitForText("LIVE BACKEND DATA")
        composeRule.runOnIdle {
            val state = viewModel.homeState.value as HomeUiState.Content
            assertEquals(5, state.briefing.papers.size)
            assertEquals(ContentOrigin.LIVE_BACKEND, state.briefing.disclosure.origin)
            assertEquals("https://arxiv.org/abs/1706.03762", repository.submittedSeed)
        }
    }

    @Test
    fun s2_cachedStartupAndUnavailableNetwork_keepsCachedContentVisible() {
        val cached =
            e4Briefing(
                ContentOrigin.CACHED_BACKEND,
                "Network unavailable; cached briefing retained.",
            )
        val viewModel =
            showApp(
                ScenarioRepository(
                    restoredBriefing = cached,
                    refreshedBriefing = cached,
                ),
            )

        waitForText("CACHED BACKEND DATA")
        composeRule.onNodeWithText(E4_PAPER_TITLE).assertIsDisplayed()
        composeRule.onNodeWithText("Network unavailable; cached briefing retained.").assertIsDisplayed()
        composeRule.runOnIdle {
            val state = viewModel.homeState.value as HomeUiState.Content
            assertEquals(ContentOrigin.CACHED_BACKEND, state.briefing.disclosure.origin)
        }
    }

    @Test
    fun s3_cachedStartupAndServerFailure_retainsDataAndFailureDisclosure() {
        val restored =
            e4Briefing(
                ContentOrigin.CACHED_BACKEND,
                "Restored while checking for updates.",
            )
        val failedRefresh =
            e4Briefing(
                ContentOrigin.CACHED_BACKEND,
                "The server refresh failed; the last successful briefing remains available.",
            )
        val viewModel =
            showApp(
                ScenarioRepository(
                    restoredBriefing = restored,
                    refreshedBriefing = failedRefresh,
                ),
            )

        waitForText("The server refresh failed; the last successful briefing remains available.")
        composeRule.onNodeWithText(E4_PAPER_TITLE).assertIsDisplayed()
        composeRule.runOnIdle {
            val state = viewModel.homeState.value as HomeUiState.Content
            assertEquals(ContentOrigin.CACHED_BACKEND, state.briefing.disclosure.origin)
            assertEquals(
                E4_PAPER_TITLE,
                state.briefing.papers
                    .single()
                    .title,
            )
        }
    }

    @Test
    fun s4_threePreparationPolls_keepPaperIdentityUntilReady() {
        val paper = requireNotNull(SeededSkeletalContentRepository.paper(SeededSkeletalContentRepository.PAPER_ID))
        val repository =
            ScenarioRepository(
                restoredBriefing = e4Briefing(ContentOrigin.LIVE_BACKEND, "Live briefing."),
                refreshedBriefing = e4Briefing(ContentOrigin.LIVE_BACKEND, "Live briefing."),
                paperResults =
                    listOf(
                        e4Processing("download_pdf"),
                        e4Processing("parse_pdf"),
                        e4Processing("summarize_paper"),
                        PaperContentResult.Ready(paper),
                    ),
            )
        val viewModel = showApp(repository)

        waitForText(E4_PAPER_TITLE)
        composeRule.onNodeWithText(E4_PAPER_TITLE).performClick()
        waitForPaperMessage(viewModel, "Downloading the source paper...")
        waitForPaperMessage(viewModel, "Extracting the paper text...")
        waitForPaperMessage(viewModel, "Generating the paper summary...")
        composeRule.waitUntil(timeoutMillis = 5_000) {
            viewModel.paperState.value is PaperDetailUiState.Content
        }
        composeRule.runOnIdle {
            val state = viewModel.paperState.value as PaperDetailUiState.Content
            assertEquals(SeededSkeletalContentRepository.PAPER_ID, state.paper.paper.id)
            assertEquals(listOf(E4_JOB_ID, E4_JOB_ID, E4_JOB_ID), repository.refreshedJobIds)
        }
    }

    @Test
    fun s5_invalidStoredBriefing_showsContractErrorWithoutFixtureSubstitution() {
        val viewModel =
            showApp(
                ScenarioRepository(
                    invalidStoredBriefing = true,
                ),
            )

        waitForText("The backend response does not match the frozen v0.1 API contract.")
        assertTrue(composeRule.onAllNodesWithText(E4_PAPER_TITLE).fetchSemanticsNodes().isEmpty())
        assertTrue(
            composeRule
                .onAllNodes(hasTestTag("seed-onboarding-screen"))
                .fetchSemanticsNodes()
                .isEmpty(),
        )
        composeRule.runOnIdle {
            assertTrue(viewModel.homeState.value is HomeUiState.Error)
            assertEquals(OnboardingUiState.Ready, viewModel.onboardingState.value)
        }
    }

    private fun showApp(repository: ScenarioRepository): MnemeViewModel {
        val viewModel = MnemeViewModel(repository)
        composeRule.setContent {
            MnemeTheme {
                mnemeApp(viewModel = viewModel, onOpenSource = {})
            }
        }
        return viewModel
    }

    private fun waitForText(text: String) {
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun waitForPaperMessage(
        viewModel: MnemeViewModel,
        message: String,
    ) {
        composeRule.waitUntil(timeoutMillis = 5_000) {
            (viewModel.paperState.value as? PaperDetailUiState.Loading)?.message == message
        }
    }
}
