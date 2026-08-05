package com.mneme.app.ui.saved

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import com.mneme.app.ui.SavedPapersUiState
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class SavedScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun emptyState_explainsHowToPopulateSavedPapers() {
        composeRule.setContent {
            MnemeTheme {
                SavedScreen(
                    state = SavedPapersUiState.Content(emptyList()),
                    onPaperClick = {},
                )
            }
        }

        composeRule.onNodeWithTag("saved-empty-state").assertIsDisplayed()
        composeRule
            .onNodeWithText("Papers you save from a briefing will appear here for quick access.")
            .assertIsDisplayed()
    }

    @Test
    fun savedPaper_opensThroughItsRealIdentifier() {
        var openedPaperId: String? = null
        val paper =
            PaperUiModel(
                id = "paper-1",
                title = "A cached paper",
                authors = "Ada, Grace",
                category = "cs.CL",
                summary = "A real cached abstract.",
            )
        composeRule.setContent {
            MnemeTheme {
                SavedScreen(
                    state = SavedPapersUiState.Content(listOf(paper)),
                    onPaperClick = { openedPaperId = it },
                )
            }
        }

        composeRule.onNodeWithTag("saved-paper-count").assertIsDisplayed()
        composeRule.onNodeWithTag("saved-screen").performScrollToNode(
            hasText("A cached paper"),
        )
        composeRule.onNodeWithText("A cached paper").assertIsDisplayed().performClick()
        composeRule.runOnIdle { assertEquals("paper-1", openedPaperId) }
    }

    @Test
    fun errorState_offersRetry() {
        var retryCount = 0
        composeRule.setContent {
            MnemeTheme {
                SavedScreen(
                    state = SavedPapersUiState.Error("Saved papers could not be loaded."),
                    onPaperClick = {},
                    onRetry = { retryCount += 1 },
                )
            }
        }

        composeRule.onNodeWithTag("saved-error").assertIsDisplayed()
        composeRule.onNodeWithText("Try again").performClick()
        composeRule.runOnIdle { assertEquals(1, retryCount) }
    }
}
