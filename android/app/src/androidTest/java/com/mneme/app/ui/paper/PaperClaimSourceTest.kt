@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.paper

import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import com.mneme.app.ui.EventRecordingStatus
import com.mneme.app.ui.model.ClaimProvenanceUiModel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel
import com.mneme.app.ui.model.SummaryClaimUiModel
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.atomic.AtomicReference

class PaperClaimSourceTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun matchedClaim_revealsRecordedLocationAndOpensSamePaper() {
        val openedUrl = AtomicReference<String>()
        showPaper(
            paper = paperDetail(listOf(matchedClaim())),
            onOpenSource = openedUrl::set,
        )

        scrollTo("claim-source-action-0")
        composeRule.onNodeWithTag("claim-source-action-0").performClick()
        scrollTo("claim-evidence-0")
        composeRule.onNodeWithText("Section: Evaluation").assertIsDisplayed()
        composeRule.onNodeWithText("Pages 6-7").assertIsDisplayed()
        composeRule
            .onNodeWithText("A synthetic excerpt from the evaluated paper.")
            .assertIsDisplayed()
        composeRule.onNodeWithTag("claim-open-paper-0").performClick()

        composeRule.runOnIdle { assertEquals(PAPER_URL, openedUrl.get()) }
    }

    @Test
    fun partialMetadata_showsExcerptWithoutInventingSectionOrPage() {
        val claim =
            matchedClaim().copy(
                source =
                    checkNotNull(matchedClaim().source).copy(
                        sectionTitle = null,
                        pageStart = null,
                        pageEnd = null,
                    ),
            )
        showPaper(paperDetail(listOf(claim)))

        scrollTo("claim-source-action-0")
        composeRule.onNodeWithTag("claim-source-action-0").performClick()
        scrollTo("claim-evidence-0")

        composeRule.onNodeWithText("Section: Paper text").assertDoesNotExist()
        composeRule.onNodeWithText("Page 6").assertDoesNotExist()
        composeRule
            .onNodeWithText("A synthetic excerpt from the evaluated paper.")
            .assertIsDisplayed()
    }

    @Test
    fun unmatchedAndLegacyClaims_haveNoSourceAction() {
        showPaper(
            paperDetail(
                listOf(
                    SummaryClaimUiModel(
                        text = "Unmatched claim",
                        matchStatus = SourceMatchUiStatus.UNMATCHED,
                    ),
                    SummaryClaimUiModel(
                        text = "Legacy claim",
                        matchStatus = SourceMatchUiStatus.NOT_CHECKED,
                    ),
                ),
            ),
        )

        scrollTo("claim-source-unavailable-0")
        composeRule.onNodeWithTag("claim-source-unavailable-0").assertIsDisplayed()
        composeRule.onNodeWithTag("claim-source-unavailable-1").assertIsDisplayed()
        composeRule.onNodeWithTag("claim-source-action-0").assertDoesNotExist()
        composeRule.onNodeWithTag("claim-source-action-1").assertDoesNotExist()
    }

    @Test
    fun expandedClaim_survivesRestoreWithoutMovingToChangedClaim() {
        val paperState = mutableStateOf(paperDetail(listOf(matchedClaim())))
        val restorationTester = StateRestorationTester(composeRule)
        restorationTester.setContent {
            MnemeTheme {
                PaperDetailScreen(
                    paper = paperState.value,
                    actions = actions(),
                    saveStatus = EventRecordingStatus.IDLE,
                    shareStatus = EventRecordingStatus.IDLE,
                )
            }
        }
        scrollTo("claim-source-action-0")
        composeRule.onNodeWithTag("claim-source-action-0").performClick()

        restorationTester.emulateSavedInstanceStateRestore()

        scrollTo("claim-evidence-0")
        composeRule.onNodeWithTag("claim-evidence-0").assertIsDisplayed()

        composeRule.runOnIdle {
            paperState.value =
                paperDetail(
                    listOf(
                        matchedClaim().copy(
                            text = "A replacement claim",
                            source =
                                checkNotNull(matchedClaim().source).copy(
                                    excerpt = "Evidence for the replacement claim.",
                                ),
                        ),
                    ),
                )
        }
        composeRule.onNodeWithTag("claim-evidence-0").assertDoesNotExist()
    }

    private fun showPaper(
        paper: PaperDetailUiModel,
        onOpenSource: (String) -> Unit = {},
    ) {
        composeRule.setContent {
            MnemeTheme {
                PaperDetailScreen(
                    paper = paper,
                    actions = actions(onOpenSource),
                    saveStatus = EventRecordingStatus.IDLE,
                    shareStatus = EventRecordingStatus.IDLE,
                )
            }
        }
    }

    private fun scrollTo(tag: String) {
        composeRule
            .onNodeWithTag("paper-detail-screen")
            .performScrollToNode(hasTestTag(tag))
    }

    private fun actions(onOpenSource: (String) -> Unit = {}) =
        PaperDetailActions(
            askQuestion = {},
            exploreGraph = {},
            savePaper = {},
            sharePaper = {},
            openSource = onOpenSource,
        )

    private fun paperDetail(claims: List<SummaryClaimUiModel>) =
        PaperDetailUiModel(
            paper =
                PaperUiModel(
                    id = "paper-1",
                    title = "Source-linked paper",
                    authors = "A. Researcher",
                    category = "cs.IR",
                    summary = "A synthetic summary.",
                ),
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.LIVE_BACKEND,
                    message = "Summary returned by the backend.",
                ),
            abstractText = "A synthetic abstract.",
            keyClaims = claims.map(SummaryClaimUiModel::text),
            methodology = null,
            limitation = null,
            sourceMatchStatus = SourceMatchUiStatus.MATCHED,
            source =
                SourceUiModel(
                    label = "Source-linked paper",
                    location = "Source paper",
                    url = PAPER_URL,
                ),
            summaryClaims = claims,
        )

    private fun matchedClaim() =
        SummaryClaimUiModel(
            text = "Measured claim",
            matchStatus = SourceMatchUiStatus.MATCHED,
            source =
                ClaimProvenanceUiModel(
                    chunkId = "33333333-3333-4333-8333-333333333333",
                    chunkIndex = 3,
                    sectionTitle = "Evaluation",
                    pageStart = 6,
                    pageEnd = 7,
                    excerpt = "A synthetic excerpt from the evaluated paper.",
                ),
        )

    private companion object {
        const val PAPER_URL = "https://arxiv.org/abs/2607.00001"
    }
}
