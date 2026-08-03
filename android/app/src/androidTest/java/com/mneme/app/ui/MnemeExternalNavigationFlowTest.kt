@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.repository.ControlledFixtureDataRepository
import com.mneme.app.ui.navigation.ExternalNavigationRequest
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class MnemeExternalNavigationFlowTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun validExternalRequest_opensLoadedPaperAndRecordsOneOpenEvent() {
        val tracker = OpenEventTracker()
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository(), tracker)
        val consumedRequestIds = mutableListOf<Long>()
        var externalRequest by
            mutableStateOf<ExternalNavigationRequest?>(
                ExternalNavigationRequest.OpenPaper(
                    requestId = VALID_REQUEST_ID,
                    paperId = SeededSkeletalContentRepository.PAPER_ID,
                ),
            )
        var recompositionToken by mutableIntStateOf(0)

        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    modifier = Modifier.testTag("external-flow-$recompositionToken"),
                    onOpenSource = {},
                    onSharePaper = { _, _ -> },
                    externalNavigation =
                        MnemeExternalNavigationBinding(
                            request = externalRequest,
                            onRequestConsumed = { requestId ->
                                consumedRequestIds += requestId
                                if (externalRequest?.requestId == requestId) {
                                    externalRequest = null
                                }
                            },
                        ),
                )
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule
                .onAllNodesWithTag("paper-detail-screen")
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Attention Is All You Need").assertIsDisplayed()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.openedPaperIds.size == 1
        }

        composeRule.runOnIdle { recompositionToken += 1 }
        composeRule.waitForIdle()

        composeRule.runOnIdle {
            assertEquals(listOf(VALID_REQUEST_ID), consumedRequestIds)
            assertEquals(
                listOf(SeededSkeletalContentRepository.PAPER_ID),
                tracker.openedPaperIds,
            )
        }
    }

    @Test
    fun unknownExternalPaper_showsRecoverableErrorAndDoesNotRecordOpenEvent() {
        val tracker = OpenEventTracker()
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository(), tracker)
        val consumedRequestIds = mutableListOf<Long>()
        var externalRequest by
            mutableStateOf<ExternalNavigationRequest?>(
                ExternalNavigationRequest.OpenPaper(
                    requestId = UNKNOWN_REQUEST_ID,
                    paperId = UNKNOWN_PAPER_ID,
                ),
            )

        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    onOpenSource = {},
                    onSharePaper = { _, _ -> },
                    externalNavigation =
                        MnemeExternalNavigationBinding(
                            request = externalRequest,
                            onRequestConsumed = { requestId ->
                                consumedRequestIds += requestId
                                if (externalRequest?.requestId == requestId) {
                                    externalRequest = null
                                }
                            },
                        ),
                )
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule
                .onAllNodesWithText("The selected paper is not available.")
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        composeRule.onNodeWithText("Something went wrong").assertIsDisplayed()
        composeRule.onNodeWithText("The selected paper is not available.").assertIsDisplayed()
        composeRule.onNodeWithText("Try again").assertIsDisplayed()

        composeRule.runOnIdle {
            assertEquals(listOf(UNKNOWN_REQUEST_ID), consumedRequestIds)
            assertTrue(tracker.openedPaperIds.isEmpty())
        }
    }

    @Test
    fun seedRequired_validExternalRequestWaitsForReadyBeforeNavigationAndConsumption() {
        val tracker = OpenEventTracker()
        val repository = ScenarioRepository(restoredBriefing = null)
        val viewModel = MnemeViewModel(repository, tracker)
        val consumedRequestIds = mutableListOf<Long>()
        var externalRequest by
            mutableStateOf<ExternalNavigationRequest?>(
                ExternalNavigationRequest.OpenPaper(
                    requestId = ONBOARDING_REQUEST_ID,
                    paperId = SeededSkeletalContentRepository.PAPER_ID,
                ),
            )

        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    onOpenSource = {},
                    onSharePaper = { _, _ -> },
                    externalNavigation =
                        MnemeExternalNavigationBinding(
                            request = externalRequest,
                            onRequestConsumed = { requestId ->
                                consumedRequestIds += requestId
                                if (externalRequest?.requestId == requestId) {
                                    externalRequest = null
                                }
                            },
                        ),
                )
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule
                .onAllNodesWithTag("seed-onboarding-screen")
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        composeRule.runOnIdle {
            assertEquals(ONBOARDING_REQUEST_ID, externalRequest?.requestId)
            assertTrue(consumedRequestIds.isEmpty())
            assertTrue(tracker.openedPaperIds.isEmpty())
        }

        composeRule
            .onNodeWithTag("seed-paper-input")
            .performTextInput("https://arxiv.org/abs/1706.03762")
        composeRule.onNodeWithTag("seed-paper-submit").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule
                .onAllNodesWithTag("paper-detail-screen")
                .fetchSemanticsNodes()
                .isNotEmpty() &&
                tracker.openedPaperIds.size == 1
        }

        composeRule.onNodeWithText("Attention Is All You Need").assertIsDisplayed()
        composeRule.runOnIdle {
            assertEquals("https://arxiv.org/abs/1706.03762", repository.submittedSeed)
            assertEquals(listOf(ONBOARDING_REQUEST_ID), consumedRequestIds)
            assertEquals(
                listOf(SeededSkeletalContentRepository.PAPER_ID),
                tracker.openedPaperIds,
            )
        }
    }

    private class OpenEventTracker : BehavioralEventTracker {
        val openedPaperIds = mutableListOf<String>()

        override suspend fun recordPaperImpressions(paperIds: List<String>) = Unit

        override suspend fun recordPaperOpened(paperId: String) {
            openedPaperIds += paperId
        }

        override suspend fun recordPaperSaved(paperId: String) = Unit

        override suspend fun recordPaperShared(paperId: String) = Unit

        override suspend fun recordQuestionAsked(paperId: String) = Unit
    }

    private companion object {
        const val VALID_REQUEST_ID = 41L
        const val UNKNOWN_REQUEST_ID = 42L
        const val ONBOARDING_REQUEST_ID = 43L
        const val UNKNOWN_PAPER_ID = "00000000-0000-0000-0000-000000000001"
    }
}
