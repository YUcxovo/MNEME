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
                    eventId = VALID_EVENT_ID,
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
                    eventId = UNKNOWN_EVENT_ID,
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
                    eventId = ONBOARDING_EVENT_ID,
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

    @Test
    fun failedDurableWrite_retriesWithoutClosingThePaperOrDuplicatingTheOpen() {
        val tracker = RetryingOpenEventTracker()
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository(), tracker)
        var externalRequest by
            mutableStateOf<ExternalNavigationRequest?>(
                ExternalNavigationRequest.OpenPaper(
                    requestId = RETRY_REQUEST_ID,
                    paperId = SeededSkeletalContentRepository.PAPER_ID,
                    eventId = RETRY_EVENT_ID,
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
                                if (externalRequest?.requestId == requestId) {
                                    externalRequest = null
                                }
                            },
                        ),
                )
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.attemptedEventIds.size == 2 && tracker.openedPaperIds.size == 1
        }
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Attention Is All You Need").assertIsDisplayed()
        composeRule.runOnIdle {
            assertEquals(listOf(RETRY_EVENT_ID, RETRY_EVENT_ID), tracker.attemptedEventIds)
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

        override suspend fun recordPaperOpenedOnce(
            eventId: String,
            paperId: String,
        ) = recordPaperOpened(paperId)

        override suspend fun recordPaperSaved(paperId: String) = Unit

        override suspend fun recordPaperShared(paperId: String) = Unit

        override suspend fun recordQuestionAsked(paperId: String) = Unit
    }

    private class RetryingOpenEventTracker : BehavioralEventTracker {
        val attemptedEventIds = mutableListOf<String>()
        val openedPaperIds = mutableListOf<String>()

        override suspend fun recordPaperImpressions(paperIds: List<String>) = Unit

        override suspend fun recordPaperOpened(paperId: String) = Unit

        override suspend fun recordPaperOpenedOnce(
            eventId: String,
            paperId: String,
        ) {
            attemptedEventIds += eventId
            if (attemptedEventIds.size == 1) {
                error("controlled Room failure")
            }
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
        const val RETRY_REQUEST_ID = 44L
        const val VALID_EVENT_ID = "11111111-1111-4111-8111-111111111111"
        const val UNKNOWN_EVENT_ID = "22222222-2222-4222-8222-222222222222"
        const val ONBOARDING_EVENT_ID = "33333333-3333-4333-8333-333333333333"
        const val RETRY_EVENT_ID = "44444444-4444-4444-8444-444444444444"
        const val UNKNOWN_PAPER_ID = "00000000-0000-0000-0000-000000000001"
    }
}
