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
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.unit.dp
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.GraphUiState
import com.mneme.app.ui.graphDestination
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
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
    fun citationGraph_opensSelectedPaperWithoutEngineeringLabels() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            )
        val openedPaper = AtomicReference<String>()
        composeRule.setContent {
            MnemeTheme {
                graphScreen(
                    graph = graph,
                    onRetry = {},
                    onOpenPaper = openedPaper::set,
                    onExploreGraph = {},
                )
            }
        }

        composeRule.onNodeWithTag("graph-screen").assertIsDisplayed()
        composeRule.onNodeWithTag("citation-graph-webview").assertIsDisplayed()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("graph-node-chooser"),
        )
        composeRule.onNodeWithTag("graph-node-chooser").performScrollToNode(
            hasTestTag("graph-node-${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}"),
        )
        composeRule
            .onNodeWithTag("graph-node-${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}")
            .performClick()
        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("selected-graph-paper-title"),
        )
        composeRule
            .onNodeWithTag("selected-graph-paper-title")
            .assertTextContains("Systems study")
        composeRule.onNodeWithTag("open-selected-graph-paper").performClick()

        composeRule.runOnIdle {
            assertEquals(SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID, openedPaper.get())
        }
    }

    @Test
    fun graphSelection_survivesSavedStateRestore() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            )
        val restorationTester = StateRestorationTester(composeRule)
        restorationTester.setContent {
            MnemeTheme {
                graphScreen(
                    graph = graph,
                    onRetry = {},
                    onOpenPaper = {},
                    onExploreGraph = {},
                )
            }
        }

        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("graph-node-chooser"),
        )
        composeRule.onNodeWithTag("graph-node-chooser").performScrollToNode(
            hasTestTag("graph-node-${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}"),
        )
        composeRule
            .onNodeWithTag("graph-node-${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}")
            .performClick()

        restorationTester.emulateSavedInstanceStateRestore()

        composeRule.onNodeWithTag("graph-screen").performScrollToNode(
            hasTestTag("selected-graph-paper-title"),
        )
        composeRule
            .onNodeWithTag("selected-graph-paper-title")
            .assertTextContains("Systems study")
    }

    @Test
    fun emptyGraph_hasTruthfulStateAndRetry() {
        val retried = AtomicBoolean(false)
        composeRule.setContent {
            MnemeTheme {
                graphScreen(
                    graph = emptyGraph(),
                    onRetry = { retried.set(true) },
                    onOpenPaper = {},
                    onExploreGraph = {},
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
                    "document.querySelectorAll('.edge').length + ':' + " +
                    "(document.querySelector('#graph').getBoundingClientRect().height > 300) + ':' + " +
                    "document.querySelectorAll('.node.center').length + ':' + " +
                    "document.querySelectorAll('.node.selected').length",
                javaScriptState::set,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            javaScriptState.get() != null
        }
        assertEquals("\"object:true:12:18:true:1:1\"", javaScriptState.get())

        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "window.MnemeGraph.selectNodeById(" +
                    "'${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}')",
                null,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            selectedPaper.get() == SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID
        }
        javaScriptState.set(null)
        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "document.querySelector('.node.selected').dataset.nodeId + ':' + " +
                    "(new Set(Array.from(document.querySelectorAll('.node circle'))" +
                    ".map(function (node) { return node.getAttribute('fill'); })).size >= 4) + ':' + " +
                    "(Array.from(document.querySelectorAll('.edge'))" +
                    ".every(function (edge) { return edge.getAttribute('marker-end') === " +
                    "'url(#citation-arrow)'; })) + ':' + " +
                    "(function () { const svg = document.querySelector('svg').getBoundingClientRect(); " +
                    "return Array.from(document.querySelectorAll('.node circle')).every(function (node) { " +
                    "const rect = node.getBoundingClientRect(); return rect.left >= svg.left && " +
                    "rect.right <= svg.right && rect.top >= svg.top && rect.bottom <= svg.bottom; }); }())",
                javaScriptState::set,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            javaScriptState.get() != null
        }
        assertEquals(
            "\"${SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID}:true:true:true\"",
            javaScriptState.get(),
        )
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
                graphDestination(
                    paperId = SeededSkeletalContentRepository.PAPER_ID,
                    state = state,
                    onRetry = { retried.set(true) },
                    onOpenPaper = {},
                    onExploreGraph = {},
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
    fun localD3Renderer_handlesBoundedFiftyNodeGraph() {
        val graph = boundedGraph()
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
                "document.querySelectorAll('.node').length + ':' + " +
                    "document.querySelectorAll('.edge').length + ':' + " +
                    "document.querySelector('svg').classList.contains('dense') + ':' + " +
                    "document.querySelectorAll('.node.center').length",
                javaScriptState::set,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            javaScriptState.get() != null
        }
        assertEquals("\"50:73:true:1\"", javaScriptState.get())

        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "window.MnemeGraph.selectNodeById('stress-paper-49')",
                null,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            selectedPaper.get() == "stress-paper-49"
        }
        javaScriptState.set(null)
        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "document.querySelector('.node.selected').dataset.nodeId + ':' + " +
                    "Array.from(document.querySelectorAll('.node text')).filter(function (label) { " +
                    "return getComputedStyle(label).display !== 'none'; }).length",
                javaScriptState::set,
            )
        }
        composeRule.waitUntil(timeoutMillis = WEBVIEW_TIMEOUT_MILLIS) {
            javaScriptState.get() != null
        }
        assertEquals("\"stress-paper-49:2\"", javaScriptState.get())
    }

    @Test
    fun readyGraph_usesProductFacingHeading() {
        val graph =
            requireNotNull(
                SeededSkeletalContentRepository.graph(SeededSkeletalContentRepository.PAPER_ID),
            ).copy(algorithmStatus = GraphAlgorithmUiStatus.READY)
        composeRule.setContent {
            MnemeTheme {
                graphScreen(
                    graph = graph,
                    onRetry = {},
                    onOpenPaper = {},
                    onExploreGraph = {},
                )
            }
        }

        composeRule.onNodeWithText("Citation connections").assertIsDisplayed()
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

    private fun boundedGraph(): GraphUiModel {
        val categories = listOf("cs.AI", "cs.CL", "cs.LG", "cs.IR", "stat.ML")
        val nodes =
            (0 until 50).map { index ->
                GraphNodeUiModel(
                    id = "stress-paper-$index",
                    title = "Bounded renderer paper $index",
                    category = categories[index % categories.size],
                    clusterId = "cluster-${index % 6}",
                    rankScore = 1.0 - index / 50.0,
                )
            }
        val chainEdges =
            (1 until 50).map { index ->
                GraphEdgeUiModel(
                    source = "stress-paper-$index",
                    target = "stress-paper-${index - 1}",
                    weight = 0.5,
                )
            }
        val crossEdges =
            (2 until 50 step 2).map { index ->
                GraphEdgeUiModel(
                    source = "stress-paper-$index",
                    target = "stress-paper-${(index + 7) % 50}",
                    weight = 0.3,
                )
            }
        return GraphUiModel(
            centerId = "stress-paper-0",
            nodes = nodes,
            edges = chainEdges + crossEdges,
            algorithmStatus = GraphAlgorithmUiStatus.READY,
            graphVersion = "bounded-renderer-stress-fixture",
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.CONTROLLED_FIXTURE,
                    message = "Controlled fifty-node renderer stress fixture.",
                ),
        )
    }

    private companion object {
        const val WEBVIEW_TIMEOUT_MILLIS = 10_000L
    }
}
