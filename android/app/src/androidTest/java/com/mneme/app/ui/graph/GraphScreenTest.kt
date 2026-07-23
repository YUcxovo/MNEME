@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import android.webkit.WebView
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.unit.dp
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.GraphDestination
import com.mneme.app.ui.GraphUiState
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

class GraphScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun fallbackGraph_disclosesOriginAndOpensSelectedPaper() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            )
        val openedPaper = AtomicReference<String>()
        composeRule.setContent {
            MnemeTheme {
                GraphScreen(
                    graph = graph,
                    onRetry = {},
                    onOpenPaper = openedPaper::set,
                )
            }
        }

        composeRule.onNodeWithTag("graph-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("citation-graph-webview").assertIsDisplayed()
        composeRule.onNodeWithTag("graph-source-notice").assertIsDisplayed()
        composeRule.onNodeWithText("Deterministic citation baseline").assertIsDisplayed()
        composeRule
            .onNodeWithTag("graph-node-${SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID}")
            .performClick()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            androidx.compose.ui.test
                .hasTestTag("selected-graph-paper-title"),
        )
        composeRule
            .onNodeWithTag("selected-graph-paper-title")
            .assertTextContains("Controlled neighbor paper")
        composeRule.onNodeWithTag("open-selected-graph-paper").performClick()

        composeRule.runOnIdle {
            assertEquals(SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID, openedPaper.get())
        }
    }

    @Test
    fun emptyGraph_hasTruthfulStateAndRetry() {
        val retried = AtomicBoolean(false)
        composeRule.setContent {
            MnemeTheme {
                GraphScreen(
                    graph = emptyGraph(),
                    onRetry = { retried.set(true) },
                    onOpenPaper = {},
                )
            }
        }

        composeRule.onNodeWithTag("graph-empty").assertIsDisplayed()
        composeRule.onNodeWithText("No citation connections yet").assertIsDisplayed()
        composeRule.onNodeWithTag("graph-empty-retry").performClick()
        assertTrue(retried.get())
    }

    @Test
    fun localD3Renderer_loadsAndBridgeSelectsKnownNode() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            )
        val webView = AtomicReference<WebView>()
        val rendererReady = AtomicBoolean(false)
        val selectedPaper = AtomicReference<String>()
        val javaScriptState = AtomicReference<String>()
        composeRule.setContent {
            CitationGraphWebView(
                graph = graph,
                onNodeSelected = selectedPaper::set,
                modifier = Modifier.height(390.dp),
                onWebViewCreated = webView::set,
                onRendererReady = { rendererReady.set(true) },
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            rendererReady.get() && webView.get() != null
        }

        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "typeof d3 + ':' + document.body.dataset.rendererReady + ':' + " +
                    "document.querySelectorAll('.node').length + ':' + " +
                    "(document.querySelector('#graph').getBoundingClientRect().height > 300)",
                javaScriptState::set,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            javaScriptState.get() != null
        }
        assertEquals("\"object:true:2:true\"", javaScriptState.get())

        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "window.MnemeGraph.selectNodeById(" +
                    "'${SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID}')",
                null,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            selectedPaper.get() == SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID
        }
    }

    @Test
    fun graphDestination_movesFromLoadingToErrorAndRetries() {
        val retried = AtomicBoolean(false)
        lateinit var showError: () -> Unit
        composeRule.setContent {
            var state by remember {
                mutableStateOf<GraphUiState>(
                    GraphUiState.Loading(SeededSkeletalContentRepository.PAPER_ID),
                )
            }
            showError = {
                state =
                    GraphUiState.Error(
                        SeededSkeletalContentRepository.PAPER_ID,
                        "Graph backend unavailable.",
                    )
            }
            MnemeTheme {
                GraphDestination(
                    paperId = SeededSkeletalContentRepository.PAPER_ID,
                    state = state,
                    onRetry = { retried.set(true) },
                    onOpenPaper = {},
                )
            }
        }

        composeRule.onNodeWithText("Loading citation connections...").assertIsDisplayed()
        composeRule.runOnIdle(showError)
        composeRule.onNodeWithText("Graph backend unavailable.").assertIsDisplayed()
        composeRule.onNodeWithText("Try again").performClick()
        assertTrue(retried.get())
    }

    @Test
    fun readyGraph_reportsRankedAndClusteredStatus() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            ).copy(algorithmStatus = GraphAlgorithmUiStatus.READY)
        composeRule.setContent {
            MnemeTheme {
                GraphScreen(
                    graph = graph,
                    onRetry = {},
                    onOpenPaper = {},
                )
            }
        }

        composeRule.onNodeWithText("Ranked and clustered graph").assertIsDisplayed()
    }

    private fun emptyGraph(): GraphUiModel =
        GraphUiModel(
            centerId = "paper-without-local-neighbors",
            nodes = emptyList(),
            edges = emptyList(),
            algorithmStatus = GraphAlgorithmUiStatus.FALLBACK,
            graphVersion = "citation-graph-v1",
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.LIVE_BACKEND,
                    message = "The backend returned no locally resolved nodes.",
                ),
        )

    private companion object {
        const val WEBVIEW_TIMEOUT_MILLIS = 10_000L
    }
}
