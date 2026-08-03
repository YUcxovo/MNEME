@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.behavior.EVENT_TRACE_PAPER_ID
import com.mneme.app.data.behavior.EventTraceRepository
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.repository.ControlledFixtureDataRepository
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.io.IOException

class MnemeAppFlowTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun skeletalFlow_reachesAnswerAndVisibleSource() {
        val openedUrls = mutableListOf<String>()
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(onOpenSource = openedUrls::add)
            }
        }

        composeRule.onNodeWithTag("briefing-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("basic-summary").assertIsDisplayed()

        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("ask-question-action"),
        )
        composeRule.onNodeWithTag("ask-question-action").performClick()

        composeRule.onNodeWithTag("qa-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("qa-question-input").assertIsDisplayed()
        composeRule.onNodeWithTag("qa-submit-question").assertIsNotEnabled()
        val question = "How does attention replace recurrent sequence processing?"
        composeRule.onNodeWithTag("qa-question-input").performTextInput(
            question,
        )
        composeRule.onNodeWithTag("qa-question-input").assertTextContains(question)
        composeRule.onNodeWithTag("qa-submit-question").assertIsEnabled().performClick()
        composeRule.onNodeWithTag("qa-screen").performScrollToNode(
            hasTestTag("qa-question"),
        )
        composeRule.onNodeWithTag("qa-question").assertIsDisplayed()
        composeRule.onNodeWithTag("qa-screen").performScrollToNode(
            hasTestTag("qa-answer"),
        )
        composeRule.onNodeWithTag("qa-answer").assertIsDisplayed()
        composeRule.onNodeWithTag("qa-screen").performScrollToNode(
            hasTestTag("qa-source-card"),
        )
        composeRule.onNodeWithTag("qa-source-card").assertIsDisplayed()
        composeRule.onNodeWithTag("qa-source-status").assertIsDisplayed()
        composeRule.onNodeWithText("Open source paper").performClick()

        composeRule.runOnIdle {
            assertEquals(
                listOf("https://arxiv.org/abs/1706.03762"),
                openedUrls,
            )
        }

        composeRule.onNodeWithTag("navigate-back").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("navigate-back").performClick()
        composeRule.onNodeWithTag("briefing-screen").assertIsDisplayed()
    }

    @Test
    fun topLevelNavigation_updatesSelectedDestination() {
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(onOpenSource = {})
            }
        }

        composeRule.onNodeWithTag("nav-briefing").assertIsSelected()
        composeRule.onNodeWithTag("nav-interests").performClick()
        composeRule.onNodeWithTag("interests-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("nav-interests").assertIsSelected()

        composeRule.onNodeWithTag("nav-saved").performClick()
        composeRule.onNodeWithTag("saved-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("nav-saved").assertIsSelected()

        composeRule.onNodeWithTag("nav-briefing").performClick()
        composeRule.onNodeWithTag("briefing-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("nav-briefing").assertIsSelected()
    }

    @Test
    fun interests_addEditRemoveSaveAndRemainVisibleAfterNavigation() {
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository())
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(viewModel = viewModel, onOpenSource = {})
            }
        }
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText("Attention Is All You Need").fetchSemanticsNodes().isNotEmpty()
        }

        composeRule.onNodeWithTag("nav-interests").performClick()
        composeRule.onNodeWithTag("interests-screen").assertIsDisplayed()
        composeRule
            .onNodeWithTag("interest-topic-0")
            .performTextReplacement("Programming languages")
        composeRule.onNodeWithTag("interest-remove-1").performClick()
        composeRule.onNodeWithTag("interests-screen").performScrollToNode(
            hasTestTag("interest-new-topic"),
        )
        composeRule
            .onNodeWithTag("interest-new-topic")
            .performTextInput("AI for software engineering")
        composeRule.onNodeWithTag("interest-add").assertIsEnabled().performClick()
        composeRule.onNodeWithTag("interests-screen").performScrollToNode(
            hasTestTag("interest-save"),
        )
        composeRule.onNodeWithTag("interest-save").assertIsEnabled().performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule
                .onAllNodesWithText("Interests saved and recommendations refreshed.")
                .fetchSemanticsNodes()
                .isNotEmpty()
        }

        composeRule.onNodeWithTag("nav-briefing").performClick()
        composeRule.onNodeWithTag("nav-interests").performClick()
        composeRule
            .onNodeWithTag("interest-topic-0")
            .assertTextContains("Programming languages")
        composeRule
            .onNodeWithTag("interest-topic-2")
            .assertTextContains("AI for software engineering")
    }

    @Test
    fun viewModelBackedApp_loadsRepositoryAndAccurateSourceStatus() {
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository())
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(viewModel = viewModel, onOpenSource = {})
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText("Attention Is All You Need").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasText("Not checked"),
        )
        composeRule.onNodeWithText("Not checked").assertIsDisplayed()
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("explore-graph-action"),
        )
        composeRule.onNodeWithTag("explore-graph-action").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText("Citation connections").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithTag("graph-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Deterministic citation baseline").assertIsDisplayed()
    }

    @Test
    fun graphFlow_opensSelectedPaperAndRestoresSelectionOnBack() {
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(onOpenSource = {})
            }
        }

        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("explore-graph-action"),
        )
        composeRule.onNodeWithTag("explore-graph-action").performClick()
        composeRule.onNodeWithTag("graph-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("graph-node-chooser"),
        )
        composeRule.onNodeWithTag("graph-node-chooser").performScrollToNode(
            hasTestTag(
                "graph-node-" +
                    com.mneme.app.data.demo.SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID,
            ),
        )
        composeRule
            .onNodeWithTag(
                "graph-node-" +
                    com.mneme.app.data.demo.SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID,
            ).performClick()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("selected-graph-paper-title"),
        )
        composeRule
            .onNodeWithTag("selected-graph-paper-title")
            .assertTextContains("Systems study")
        composeRule.onNodeWithTag("open-selected-graph-paper").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Systems study").assertIsDisplayed()

        composeRule.onNodeWithTag("navigate-back").performClick()
        composeRule.onNodeWithTag("graph-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("selected-graph-paper-title"),
        )
        composeRule
            .onNodeWithTag("selected-graph-paper-title")
            .assertTextContains("Systems study")
    }

    @Test
    fun viewModelBackedApp_forwardsMvpInteractionsToEventTracker() {
        val tracker = RecordingBehavioralEventTracker()
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository(), tracker)
        val sharedPapers = mutableListOf<Pair<String, String>>()
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    onOpenSource = {},
                    onSharePaper = { title, url -> sharedPapers += title to url },
                )
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.impressionBatches.isNotEmpty()
        }
        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.openedPaperIds.isNotEmpty()
        }
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("save-paper-action"),
        )
        composeRule.onNodeWithTag("save-paper-action").performClick()
        composeRule.onNodeWithTag("save-paper-action").assertIsNotEnabled()
        composeRule.onNodeWithTag("share-paper-action").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.savedPaperIds.isNotEmpty() && tracker.sharedPaperIds.isNotEmpty()
        }
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("ask-question-action"),
        )
        composeRule.onNodeWithTag("ask-question-action").performClick()
        composeRule.onNodeWithTag("qa-question-input").performTextInput(
            "What mechanism replaces recurrence?",
        )
        composeRule.onNodeWithTag("qa-submit-question").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            tracker.questionPaperIds.isNotEmpty()
        }

        composeRule.runOnIdle {
            val paperId = SeededSkeletalContentRepository.PAPER_ID
            assertEquals(listOf(listOf(paperId)), tracker.impressionBatches)
            assertEquals(listOf(paperId), tracker.openedPaperIds)
            assertEquals(listOf(paperId), tracker.savedPaperIds)
            assertEquals(listOf(paperId), tracker.sharedPaperIds)
            assertEquals(listOf(paperId), tracker.questionPaperIds)
            assertEquals(
                listOf(
                    "Attention Is All You Need" to "https://arxiv.org/abs/1706.03762",
                ),
                sharedPapers,
            )
        }
    }

    @Test
    fun failedSaveWriteStaysVisibleAndCanBeRetried() {
        val tracker = RecordingBehavioralEventTracker(saveFailuresRemaining = 1)
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository(), tracker)
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(viewModel = viewModel, onOpenSource = {}, onSharePaper = { _, _ -> })
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText("Attention Is All You Need").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("save-paper-action"),
        )
        composeRule.onNodeWithTag("save-paper-action").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            viewModel.behavioralEvents.engagementState.value.saveStatus(
                SeededSkeletalContentRepository.PAPER_ID,
            ) == EventRecordingStatus.FAILED
        }
        composeRule.onNodeWithTag("save-paper-action").assertIsEnabled()
        composeRule
            .onNodeWithText("Save was not recorded. Tap Retry save to try again.")
            .assertIsDisplayed()

        composeRule.onNodeWithTag("save-paper-action").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            viewModel.behavioralEvents.engagementState.value.saveStatus(
                SeededSkeletalContentRepository.PAPER_ID,
            ) == EventRecordingStatus.RECORDED
        }

        composeRule.onNodeWithTag("save-paper-action").assertIsNotEnabled()
        composeRule.runOnIdle {
            assertEquals(2, tracker.saveAttempts)
            assertEquals(
                listOf(SeededSkeletalContentRepository.PAPER_ID),
                tracker.savedPaperIds,
            )
        }
    }

    @Test
    fun followUpQuestionsRemainInOnePaperConversation() {
        val viewModel = MnemeViewModel(ControlledFixtureDataRepository())
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(viewModel = viewModel, onOpenSource = {}, onSharePaper = { _, _ -> })
            }
        }

        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText("Attention Is All You Need").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("Attention Is All You Need").performClick()
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("ask-question-action"),
        )
        composeRule.onNodeWithTag("ask-question-action").performClick()

        val firstQuestion = "What replaces recurrence?"
        val secondQuestion = "How is position represented?"
        composeRule.onNodeWithTag("qa-question-input").performTextInput(firstQuestion)
        composeRule.onNodeWithTag("qa-submit-question").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            (viewModel.qaState.value as? QaUiState.Content)?.exchanges?.size == 1
        }
        composeRule.onNodeWithTag("qa-question-input").performTextInput(secondQuestion)
        composeRule.onNodeWithTag("qa-submit-question").performClick()
        composeRule.waitUntil(timeoutMillis = 5_000) {
            (viewModel.qaState.value as? QaUiState.Content)?.exchanges?.size == 2
        }

        composeRule.runOnIdle {
            val exchanges = (viewModel.qaState.value as QaUiState.Content).exchanges
            assertEquals(2, exchanges.size)
            assertEquals(1, exchanges.map { it.conversationId }.distinct().size)
        }
        composeRule.onNodeWithTag("qa-screen").performScrollToNode(hasText(firstQuestion))
        composeRule.onNodeWithText(firstQuestion).assertIsDisplayed()
        composeRule.onNodeWithTag("qa-screen").performScrollToNode(hasText(secondQuestion))
        composeRule.onNodeWithText(secondQuestion).assertIsDisplayed()
    }

    @Test
    fun viewModelKeepsConversationIdentityScopedToOnePaper() {
        val repository = EventTraceRepository()
        val viewModel = MnemeViewModel(repository)
        val otherPaperId = "a11abac8-45e7-4c47-93c0-5be0bb391b03"

        composeRule.runOnIdle {
            viewModel.openQa(EVENT_TRACE_PAPER_ID)
            viewModel.askQuestion(EVENT_TRACE_PAPER_ID, "First question")
        }
        composeRule.waitUntil(timeoutMillis = 5_000) {
            (viewModel.qaState.value as? QaUiState.Content)?.exchanges?.size == 1
        }
        composeRule.runOnIdle {
            viewModel.askQuestion(EVENT_TRACE_PAPER_ID, "Follow-up question")
        }
        composeRule.waitUntil(timeoutMillis = 5_000) {
            (viewModel.qaState.value as? QaUiState.Content)?.exchanges?.size == 2
        }
        composeRule.runOnIdle {
            viewModel.openQa(otherPaperId)
            viewModel.askQuestion(otherPaperId, "Different paper question")
        }
        composeRule.waitUntil(timeoutMillis = 5_000) {
            val state = viewModel.qaState.value as? QaUiState.Content
            state?.paperId == otherPaperId && state.exchanges.size == 1
        }

        composeRule.runOnIdle {
            assertEquals(
                listOf(null, "event-trace-$EVENT_TRACE_PAPER_ID", null),
                repository.requestedConversationIds,
            )
        }
    }

    private class RecordingBehavioralEventTracker(
        private var saveFailuresRemaining: Int = 0,
    ) : BehavioralEventTracker {
        val impressionBatches = mutableListOf<List<String>>()
        val openedPaperIds = mutableListOf<String>()
        val savedPaperIds = mutableListOf<String>()
        val sharedPaperIds = mutableListOf<String>()
        val questionPaperIds = mutableListOf<String>()
        var saveAttempts = 0

        override suspend fun recordPaperImpressions(paperIds: List<String>) {
            impressionBatches += paperIds
        }

        override suspend fun recordPaperOpened(paperId: String) {
            openedPaperIds += paperId
        }

        override suspend fun recordPaperSaved(paperId: String) {
            saveAttempts += 1
            if (saveFailuresRemaining > 0) {
                saveFailuresRemaining -= 1
                throw IOException("Room write failed")
            }
            savedPaperIds += paperId
        }

        override suspend fun recordPaperShared(paperId: String) {
            sharedPaperIds += paperId
        }

        override suspend fun recordQuestionAsked(paperId: String) {
            questionPaperIds += paperId
        }
    }
}
