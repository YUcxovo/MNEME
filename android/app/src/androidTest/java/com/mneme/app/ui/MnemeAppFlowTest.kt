@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import com.mneme.app.data.repository.ControlledFixtureDataRepository
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

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
        composeRule.onNodeWithText("Not checked").assertIsDisplayed()
    }
}
