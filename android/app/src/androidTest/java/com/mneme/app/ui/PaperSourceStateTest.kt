@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.atomic.AtomicBoolean

class PaperSourceStateTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun loadingSummary_keepsExplicitProgressState() {
        showDestination(
            PaperDetailUiState.Loading(
                paperId = PAPER_ID,
                message = "Preparing the source-linked summary...",
            ),
        )

        composeRule
            .onNodeWithText("Preparing the source-linked summary...")
            .assertIsDisplayed()
    }

    @Test
    fun failedSummary_keepsRetryAction() {
        val retried = AtomicBoolean(false)
        showDestination(
            state = PaperDetailUiState.Error(PAPER_ID, "The summary is unavailable."),
            onRetry = { retried.set(true) },
        )

        composeRule.onNodeWithText("The summary is unavailable.").assertIsDisplayed()
        composeRule.onNodeWithText("Try again").performClick()
        assertTrue(retried.get())
    }

    @Test
    fun summaryWithoutClaims_keepsPaperContentVisible() {
        showDestination(PaperDetailUiState.Content(emptyClaimPaper()))

        composeRule.onNodeWithTag("paper-detail-screen").assertIsDisplayed()
        composeRule.onNodeWithText("Summary without claims.").assertIsDisplayed()
    }

    private fun showDestination(
        state: PaperDetailUiState,
        onRetry: () -> Unit = {},
    ) {
        composeRule.setContent {
            MnemeTheme {
                PaperDestination(
                    paperId = PAPER_ID,
                    state = state,
                    saveStatus = EventRecordingStatus.IDLE,
                    shareStatus = EventRecordingStatus.IDLE,
                    actions =
                        PaperDestinationActions(
                            retry = onRetry,
                            askQuestion = {},
                            exploreGraph = {},
                            savePaper = {},
                            sharePaper = {},
                            openSource = {},
                        ),
                )
            }
        }
    }

    private fun emptyClaimPaper(): PaperDetailUiModel =
        PaperDetailUiModel(
            paper =
                PaperUiModel(
                    id = PAPER_ID,
                    title = "Paper without claims",
                    authors = "A. Researcher",
                    category = "cs.IR",
                    summary = "Summary without claims.",
                ),
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.LIVE_BACKEND,
                    message = "Summary returned by the backend.",
                ),
            abstractText = "Synthetic abstract.",
            keyClaims = emptyList(),
            methodology = null,
            limitation = null,
            sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
            source =
                SourceUiModel(
                    label = "Paper without claims",
                    location = "Source paper",
                    url = "https://arxiv.org/abs/2607.00001",
                ),
        )

    private companion object {
        const val PAPER_ID = "11111111-1111-4111-8111-111111111111"
    }
}
