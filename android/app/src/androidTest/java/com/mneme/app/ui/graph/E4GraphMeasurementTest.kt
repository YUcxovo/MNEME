@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import android.os.SystemClock
import android.webkit.WebView
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.evaluation.E4MeasurementFiles
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class E4GraphMeasurementTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun recordBoundedRendererAndSelectionLatency() {
        E4MeasurementFiles.resetCsv(GRAPH_FILE, GRAPH_HEADER)
        val graphState = mutableStateOf(graph(nodeCount = 1, marker = "initial"))
        val renderKey = mutableIntStateOf(0)
        val webView = AtomicReference<WebView>()
        val rendererReadyCount = AtomicInteger()
        val selectedPaper = AtomicReference<String>()
        val initialReadyCount = rendererReadyCount.get()
        composeRule.setContent {
            key(renderKey.intValue) {
                CitationGraphWebView(
                    graph = graphState.value,
                    onNodeSelected = selectedPaper::set,
                    modifier = Modifier.height(390.dp),
                    onWebViewCreated = webView::set,
                    onRendererReady = { rendererReadyCount.incrementAndGet() },
                )
            }
        }
        check(waitForRenderer(initialReadyCount, webView, rendererReadyCount))

        var failures = 0
        NODE_COUNTS.forEach { nodeCount ->
            val edgeCount = edgeCount(nodeCount)
            repeat(COLD_WARMUPS + COLD_ITERATIONS) { index ->
                val marker = "cold-$nodeCount-$index"
                val readyBefore = rendererReadyCount.get()
                webView.set(null)
                selectedPaper.set(null)
                val startedAt = SystemClock.elapsedRealtimeNanos()
                composeRule.runOnIdle {
                    graphState.value = graph(nodeCount, marker)
                    renderKey.intValue += 1
                }
                val renderSuccess =
                    waitForRenderer(readyBefore, webView, rendererReadyCount) &&
                        waitForGraphDom(webView, nodeCount, marker)
                val renderDuration = elapsedMillis(startedAt)
                val measured = index >= COLD_WARMUPS
                if (measured) {
                    failures += if (renderSuccess) 0 else 1
                    recordGraphSample(
                        scenario = "render_ready",
                        nodeCount = nodeCount,
                        edgeCount = edgeCount,
                        phase = "cold_webview",
                        iteration = index - COLD_WARMUPS + 1,
                        durationMillis = renderDuration,
                        success = renderSuccess,
                        outcome = if (renderSuccess) "dom_ready" else "timeout",
                    )
                }
                if (renderSuccess) {
                    val selection = measureSelection(webView, selectedPaper, "graph-paper-${nodeCount - 1}")
                    if (measured) {
                        failures += if (selection.success) 0 else 1
                        recordGraphSample(
                            scenario = "select_node",
                            nodeCount = nodeCount,
                            edgeCount = edgeCount,
                            phase = "cold_webview",
                            iteration = index - COLD_WARMUPS + 1,
                            durationMillis = selection.durationMillis,
                            success = selection.success,
                            outcome = if (selection.success) "callback_received" else "timeout",
                        )
                    }
                }
            }

            repeat(WARM_WARMUPS + WARM_ITERATIONS) { index ->
                val marker = "warm-$nodeCount-$index"
                selectedPaper.set(null)
                val startedAt = SystemClock.elapsedRealtimeNanos()
                composeRule.runOnIdle {
                    graphState.value = graph(nodeCount, marker)
                }
                val renderSuccess = waitForGraphDom(webView, nodeCount, marker)
                val renderDuration = elapsedMillis(startedAt)
                val measured = index >= WARM_WARMUPS
                if (measured) {
                    failures += if (renderSuccess) 0 else 1
                    recordGraphSample(
                        scenario = "render_ready",
                        nodeCount = nodeCount,
                        edgeCount = edgeCount,
                        phase = "warm_update",
                        iteration = index - WARM_WARMUPS + 1,
                        durationMillis = renderDuration,
                        success = renderSuccess,
                        outcome = if (renderSuccess) "dom_ready" else "timeout",
                    )
                }
                if (renderSuccess) {
                    val selection = measureSelection(webView, selectedPaper, "graph-paper-${nodeCount - 1}")
                    if (measured) {
                        failures += if (selection.success) 0 else 1
                        recordGraphSample(
                            scenario = "select_node",
                            nodeCount = nodeCount,
                            edgeCount = edgeCount,
                            phase = "warm_update",
                            iteration = index - WARM_WARMUPS + 1,
                            durationMillis = selection.durationMillis,
                            success = selection.success,
                            outcome = if (selection.success) "callback_received" else "timeout",
                        )
                    }
                }
            }
        }

        assertEquals("Every measured graph sample must complete.", 0, failures)
    }

    @Test
    fun recordReadyFallbackAndEmptyStateDisclosureReliability() {
        E4MeasurementFiles.resetCsv(GRAPH_STATE_FILE, GRAPH_STATE_HEADER)
        val graphState = mutableStateOf(graph(12, "state-ready", GraphAlgorithmUiStatus.READY))
        composeRule.setContent {
            MnemeTheme {
                graphScreen(
                    graph = graphState.value,
                    onRetry = {},
                    onOpenPaper = {},
                )
            }
        }

        var failures = 0
        val scenarios =
            listOf(
                GraphStateScenario(
                    name = "ready",
                    graph = graph(12, "state-ready", GraphAlgorithmUiStatus.READY),
                    expectedText = "Ranked and clustered graph",
                ),
                GraphStateScenario(
                    name = "fallback",
                    graph = graph(12, "state-fallback", GraphAlgorithmUiStatus.FALLBACK),
                    expectedText = "Deterministic citation baseline",
                ),
                GraphStateScenario(
                    name = "empty",
                    graph = emptyGraph(),
                    expectedText = "No citation connections yet",
                ),
            )
        scenarios.forEach { scenario ->
            repeat(STATE_WARMUPS + STATE_ITERATIONS) { index ->
                val startedAt = SystemClock.elapsedRealtimeNanos()
                composeRule.runOnIdle {
                    graphState.value =
                        scenario.graph.copy(
                            graphVersion = "${scenario.name}-state-$index",
                        )
                }
                val success =
                    composeRule.waitUntilOrFalse(STATE_TIMEOUT_MILLIS) {
                        composeRule
                            .onAllNodesWithText(scenario.expectedText)
                            .fetchSemanticsNodes()
                            .isNotEmpty()
                    }
                val measured = index >= STATE_WARMUPS
                if (measured) {
                    failures += if (success) 0 else 1
                    E4MeasurementFiles.appendCsv(
                        GRAPH_STATE_FILE,
                        listOf(
                            "graph",
                            "status_disclosure",
                            scenario.name,
                            index - STATE_WARMUPS + 1,
                            elapsedMillis(startedAt),
                            success,
                            if (success) "visible" else "timeout",
                        ),
                    )
                }
            }
        }
        assertEquals("Every graph status must remain visible.", 0, failures)
    }

    private fun waitForRenderer(
        readyBefore: Int,
        webView: AtomicReference<WebView>,
        rendererReadyCount: AtomicInteger,
    ): Boolean =
        composeRule.waitUntilOrFalse(RENDER_TIMEOUT_MILLIS) {
            webView.get() != null && rendererReadyCount.get() > readyBefore
        }

    private fun waitForGraphDom(
        webView: AtomicReference<WebView>,
        nodeCount: Int,
        marker: String,
    ): Boolean {
        val expected = "\"true:$nodeCount:true\""
        val result = AtomicReference<String>()
        val script =
            "document.body.dataset.rendererReady + ':' + " +
                "document.querySelectorAll('.node').length + ':' + " +
                "(document.querySelector('.node title').textContent.indexOf('$marker') >= 0)"
        return composeRule.waitUntilOrFalse(RENDER_TIMEOUT_MILLIS) {
            if (result.get() != expected) {
                webView.get()?.let { current ->
                    composeRule.runOnIdle {
                        current.evaluateJavascript(script, result::set)
                    }
                }
            }
            result.get() == expected
        }
    }

    private fun measureSelection(
        webView: AtomicReference<WebView>,
        selectedPaper: AtomicReference<String>,
        paperId: String,
    ): TimedResult {
        selectedPaper.set(null)
        val startedAt = SystemClock.elapsedRealtimeNanos()
        composeRule.runOnIdle {
            webView.get().evaluateJavascript(
                "window.MnemeGraph.selectNodeById('$paperId')",
                null,
            )
        }
        val success =
            composeRule.waitUntilOrFalse(SELECTION_TIMEOUT_MILLIS) {
                selectedPaper.get() == paperId
            }
        return TimedResult(elapsedMillis(startedAt), success)
    }

    private fun recordGraphSample(
        scenario: String,
        nodeCount: Int,
        edgeCount: Int,
        phase: String,
        iteration: Int,
        durationMillis: Double,
        success: Boolean,
        outcome: String,
    ) {
        E4MeasurementFiles.appendCsv(
            GRAPH_FILE,
            listOf(
                "graph",
                scenario,
                nodeCount,
                edgeCount,
                GraphAlgorithmUiStatus.READY.name,
                phase,
                iteration,
                durationMillis,
                success,
                outcome,
            ),
        )
    }

    private fun graph(
        nodeCount: Int,
        marker: String,
        status: GraphAlgorithmUiStatus = GraphAlgorithmUiStatus.READY,
    ): GraphUiModel {
        require(nodeCount in 1..MAX_GRAPH_NODES)
        val categories = listOf("cs.AI", "cs.CL", "cs.LG", "cs.IR", "stat.ML")
        val nodes =
            (0 until nodeCount).map { index ->
                GraphNodeUiModel(
                    id = "graph-paper-$index",
                    title = "$marker paper $index",
                    category = categories[index % categories.size],
                    clusterId = "cluster-${index % 6}",
                    rankScore = 1.0 - index.toDouble() / nodeCount,
                )
            }
        val chainEdges =
            (1 until nodeCount).map { index ->
                GraphEdgeUiModel(
                    source = "graph-paper-$index",
                    target = "graph-paper-${index - 1}",
                    weight = 0.5,
                )
            }
        val crossEdges =
            (2 until nodeCount step 2).map { index ->
                GraphEdgeUiModel(
                    source = "graph-paper-$index",
                    target = "graph-paper-${(index + 7) % nodeCount}",
                    weight = 0.3,
                )
            }
        return GraphUiModel(
            centerId = "graph-paper-0",
            nodes = nodes,
            edges = chainEdges + crossEdges,
            algorithmStatus = status,
            graphVersion = "e4-render-measurement-v1",
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.CONTROLLED_FIXTURE,
                    message = "Controlled bounded renderer measurement.",
                ),
        )
    }

    private fun emptyGraph(): GraphUiModel =
        GraphUiModel(
            centerId = "empty-center",
            nodes = emptyList(),
            edges = emptyList(),
            algorithmStatus = GraphAlgorithmUiStatus.FALLBACK,
            graphVersion = "e4-empty-measurement-v1",
            disclosure =
                ContentDisclosureUiModel(
                    origin = ContentOrigin.CONTROLLED_FIXTURE,
                    message = "Controlled empty graph measurement.",
                ),
        )

    private fun edgeCount(nodeCount: Int): Int = (1 until nodeCount).count() + (2 until nodeCount step 2).count()

    private fun elapsedMillis(startedAtNanos: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAtNanos) / NANOS_PER_MILLISECOND

    private fun androidx.compose.ui.test.junit4.ComposeContentTestRule.waitUntilOrFalse(
        timeoutMillis: Long,
        condition: () -> Boolean,
    ): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMillis
        while (SystemClock.elapsedRealtime() < deadline) {
            waitForIdle()
            if (condition()) {
                return true
            }
            Thread.sleep(2)
        }
        return condition()
    }

    private data class TimedResult(
        val durationMillis: Double,
        val success: Boolean,
    )

    private data class GraphStateScenario(
        val name: String,
        val graph: GraphUiModel,
        val expectedText: String,
    )

    private companion object {
        const val GRAPH_FILE = "graph_measurements.csv"
        const val GRAPH_STATE_FILE = "graph_state_measurements.csv"
        const val MAX_GRAPH_NODES = 50
        const val COLD_WARMUPS = 2
        const val COLD_ITERATIONS = 20
        const val WARM_WARMUPS = 3
        const val WARM_ITERATIONS = 30
        const val STATE_WARMUPS = 3
        const val STATE_ITERATIONS = 30
        const val RENDER_TIMEOUT_MILLIS = 10_000L
        const val SELECTION_TIMEOUT_MILLIS = 3_000L
        const val STATE_TIMEOUT_MILLIS = 3_000L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        val NODE_COUNTS = listOf(1, 12, 25, 50)
        val GRAPH_HEADER =
            listOf(
                "track",
                "scenario",
                "node_count",
                "edge_count",
                "algorithm_status",
                "phase",
                "iteration",
                "duration_ms",
                "success",
                "outcome",
            )
        val GRAPH_STATE_HEADER =
            listOf(
                "track",
                "scenario",
                "state",
                "iteration",
                "duration_ms",
                "success",
                "outcome",
            )
    }
}
