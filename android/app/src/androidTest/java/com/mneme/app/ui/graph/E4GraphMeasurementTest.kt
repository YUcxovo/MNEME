@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import android.os.SystemClock
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class E4GraphMeasurementTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun recordBoundedRendererLatency() {
        val arguments = InstrumentationRegistry.getArguments()
        val sessionId = arguments.getString(SESSION_ID_ARGUMENT)?.takeIf(String::isNotBlank) ?: "standalone"
        val nodeCounts = parseNodeOrder(arguments.getString(NODE_ORDER_ARGUMENT))
        val warmupPairs =
            parsePairCount(
                arguments.getString(WARMUP_PAIRS_ARGUMENT),
                defaultValue = DEFAULT_WARMUP_PAIRS,
                argumentName = WARMUP_PAIRS_ARGUMENT,
                allowZero = true,
            )
        val measuredPairs =
            parsePairCount(
                arguments.getString(MEASURED_PAIRS_ARGUMENT),
                defaultValue = DEFAULT_MEASURED_PAIRS,
                argumentName = MEASURED_PAIRS_ARGUMENT,
                allowZero = false,
            )
        E4MeasurementFiles.resetCsv(GRAPH_FILE, GRAPH_HEADER)
        val graphState = mutableStateOf(graph(nodeCount = 1, marker = BOOTSTRAP_MARKER))
        val renderKey = mutableIntStateOf(0)
        val submissions = LinkedBlockingQueue<GraphRenderSubmission>()
        val completions = LinkedBlockingQueue<GraphRenderCompletion>()
        val measurementObserver =
            object : GraphRenderMeasurementObserver {
                override fun onRenderSubmitted(submission: GraphRenderSubmission) {
                    submissions.offer(submission)
                }

                override fun onVisualStateReady(completion: GraphRenderCompletion) {
                    completions.offer(completion)
                }
            }
        composeRule.setContent {
            key(renderKey.intValue) {
                CitationGraphWebView(
                    graph = graphState.value,
                    onNodeSelected = {},
                    modifier = Modifier.height(390.dp),
                    measurementObserver = measurementObserver,
                )
            }
        }
        checkBootstrapRender(submissions, completions)

        var failures = 0
        var previousNewWebViewInstanceId: Long? = null
        nodeCounts.forEachIndexed { nodeOrderIndex, nodeCount ->
            val edgeCount = edgeCount(nodeCount)
            repeat(warmupPairs + measuredPairs) { index ->
                val measured = index >= warmupPairs
                val pairIndex = index - warmupPairs + 1
                val markerPrefix =
                    if (measured) {
                        "measured-$nodeCount-$pairIndex"
                    } else {
                        "warmup-$nodeCount-${index + 1}"
                    }
                val newWebViewMarker = "$markerPrefix-A"
                val reusedWebViewMarker = "$markerPrefix-B"
                val newWebViewSample =
                    measureVisualStateReady(
                        marker = newWebViewMarker,
                        expectedNodeCount = nodeCount,
                        expectedEdgeCount = edgeCount,
                        submissions = submissions,
                        completions = completions,
                    ) {
                        graphState.value = graph(nodeCount, newWebViewMarker)
                        renderKey.intValue += 1
                    }.validateNewWebView(previousNewWebViewInstanceId)
                previousNewWebViewInstanceId =
                    newWebViewSample.webViewInstanceId ?: previousNewWebViewInstanceId

                val reusedWebViewSample =
                    measureVisualStateReady(
                        marker = reusedWebViewMarker,
                        expectedNodeCount = nodeCount,
                        expectedEdgeCount = edgeCount,
                        submissions = submissions,
                        completions = completions,
                    ) {
                        graphState.value = graph(nodeCount, reusedWebViewMarker)
                    }.validateReusedWebView(newWebViewSample.webViewInstanceId)

                if (!measured) {
                    check(newWebViewSample.success && reusedWebViewSample.success) {
                        "Graph warm-up failed for $nodeCount nodes: " +
                            "${newWebViewSample.outcome}, ${reusedWebViewSample.outcome}"
                    }
                } else {
                    failures += if (newWebViewSample.success) 0 else 1
                    failures += if (reusedWebViewSample.success) 0 else 1
                    recordGraphSample(
                        sessionId = sessionId,
                        nodeOrderIndex = nodeOrderIndex + 1,
                        pairIndex = pairIndex,
                        nodeCount = nodeCount,
                        edgeCount = edgeCount,
                        phase = PHASE_NEW_WEB_VIEW,
                        sample = newWebViewSample,
                    )
                    recordGraphSample(
                        sessionId = sessionId,
                        nodeOrderIndex = nodeOrderIndex + 1,
                        pairIndex = pairIndex,
                        nodeCount = nodeCount,
                        edgeCount = edgeCount,
                        phase = PHASE_REUSED_WEB_VIEW,
                        sample = reusedWebViewSample,
                    )
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
                GraphScreen(
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

    private fun checkBootstrapRender(
        submissions: LinkedBlockingQueue<GraphRenderSubmission>,
        completions: LinkedBlockingQueue<GraphRenderCompletion>,
    ) {
        val deadline = SystemClock.elapsedRealtime() + RENDER_TIMEOUT_MILLIS
        val submission =
            pollMatching(submissions, deadline) { candidate ->
                candidate.requestTag == BOOTSTRAP_MARKER
            }
        check(submission != null) { "The graph renderer did not submit its bootstrap payload." }
        val completion =
            pollMatching(completions, deadline) { candidate ->
                candidate.renderId == submission.renderId
            }
        check(completion != null) { "The graph renderer did not complete its bootstrap visual state." }
        check(
            completion.nodeCount == 1 &&
                completion.edgeCount == 0 &&
                completion.tickCount >= 1,
        ) {
            "The graph renderer produced an invalid bootstrap visual state."
        }
    }

    private fun measureVisualStateReady(
        marker: String,
        expectedNodeCount: Int,
        expectedEdgeCount: Int,
        submissions: LinkedBlockingQueue<GraphRenderSubmission>,
        completions: LinkedBlockingQueue<GraphRenderCompletion>,
        updateGraph: () -> Unit,
    ): GraphMeasurement {
        var startedAtNanos = 0L
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            startedAtNanos = SystemClock.elapsedRealtimeNanos()
            updateGraph()
        }
        // Drive the pending Compose update without waiting for WebView/D3 idleness.
        // The native visual-state callback records the measurement endpoint.
        composeRule.mainClock.advanceTimeByFrame()
        val deadline = SystemClock.elapsedRealtime() + RENDER_TIMEOUT_MILLIS
        val submission =
            pollMatching(submissions, deadline) { candidate ->
                candidate.requestTag == marker
            }
                ?: return GraphMeasurement.timeout(
                    durationMillis = elapsedMillis(startedAtNanos),
                    outcome = "submission_timeout",
                )
        val completion =
            pollMatching(completions, deadline) { candidate ->
                candidate.renderId == submission.renderId
            }
                ?: return GraphMeasurement.timeout(
                    renderId = submission.renderId,
                    webViewInstanceId = submission.webViewInstanceId,
                    durationMillis = elapsedMillis(startedAtNanos),
                    outcome = "visual_state_timeout",
                )
        val durationMillis =
            (completion.completedAtNanos - startedAtNanos) / NANOS_PER_MILLISECOND
        val outcome =
            when {
                completion.requestTag != marker -> "request_tag_mismatch"
                completion.webViewInstanceId != submission.webViewInstanceId ->
                    "webview_instance_mismatch"
                completion.nodeCount != expectedNodeCount -> "node_count_mismatch"
                completion.edgeCount != expectedEdgeCount -> "edge_count_mismatch"
                completion.tickCount < 1 -> "simulation_tick_missing"
                else -> "visual_state_ready"
            }
        return GraphMeasurement(
            renderId = submission.renderId,
            webViewInstanceId = submission.webViewInstanceId,
            durationMillis = durationMillis,
            domNodeCount = completion.nodeCount,
            domEdgeCount = completion.edgeCount,
            tickCount = completion.tickCount,
            success = outcome == "visual_state_ready",
            outcome = outcome,
        )
    }

    private fun recordGraphSample(
        sessionId: String,
        nodeOrderIndex: Int,
        pairIndex: Int,
        nodeCount: Int,
        edgeCount: Int,
        phase: String,
        sample: GraphMeasurement,
    ) {
        E4MeasurementFiles.appendCsv(
            GRAPH_FILE,
            listOf(
                "graph",
                "visual_state_ready",
                sessionId,
                nodeOrderIndex,
                pairIndex,
                nodeCount,
                edgeCount,
                phase,
                sample.renderId,
                sample.webViewInstanceId,
                sample.durationMillis,
                sample.domNodeCount,
                sample.domEdgeCount,
                sample.tickCount,
                sample.success,
                sample.outcome,
            ),
        )
    }

    private fun parseNodeOrder(rawOrder: String?): List<Int> {
        if (rawOrder.isNullOrBlank()) {
            return NODE_COUNTS
        }
        val parsed =
            rawOrder
                .split(",")
                .map { value ->
                    value.trim().toIntOrNull()
                        ?: throw IllegalArgumentException(
                            "$NODE_ORDER_ARGUMENT must contain comma-separated integers.",
                        )
                }
        require(parsed.size == NODE_COUNTS.size && parsed.toSet() == NODE_COUNTS.toSet()) {
            "$NODE_ORDER_ARGUMENT must be a permutation of ${NODE_COUNTS.joinToString(",")}."
        }
        return parsed
    }

    private fun parsePairCount(
        rawValue: String?,
        defaultValue: Int,
        argumentName: String,
        allowZero: Boolean,
    ): Int {
        val value = rawValue?.toIntOrNull() ?: defaultValue
        val validRange = if (allowZero) 0..MAX_PAIR_COUNT else 1..MAX_PAIR_COUNT
        require(value in validRange) {
            "$argumentName must be in ${validRange.first}..${validRange.last}."
        }
        return value
    }

    private fun <T> pollMatching(
        queue: LinkedBlockingQueue<T>,
        deadlineMillis: Long,
        predicate: (T) -> Boolean,
    ): T? {
        while (true) {
            val remainingMillis = deadlineMillis - SystemClock.elapsedRealtime()
            if (remainingMillis <= 0) {
                return null
            }
            val candidate = queue.poll(remainingMillis, TimeUnit.MILLISECONDS) ?: return null
            if (predicate(candidate)) {
                return candidate
            }
        }
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
                    title = "$nodeCount-node graph paper $index",
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
            graphVersion = marker,
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

    private data class GraphMeasurement(
        val renderId: Long?,
        val webViewInstanceId: Long?,
        val durationMillis: Double,
        val domNodeCount: Int?,
        val domEdgeCount: Int?,
        val tickCount: Int?,
        val success: Boolean,
        val outcome: String,
    ) {
        fun validateNewWebView(previousInstanceId: Long?): GraphMeasurement {
            if (!success || previousInstanceId == null || webViewInstanceId != previousInstanceId) {
                return this
            }
            return copy(
                success = false,
                outcome = "webview_not_recreated",
            )
        }

        fun validateReusedWebView(expectedInstanceId: Long?): GraphMeasurement {
            if (!success) {
                return this
            }
            if (expectedInstanceId != null && webViewInstanceId == expectedInstanceId) {
                return this
            }
            return copy(
                success = false,
                outcome = "webview_reuse_mismatch",
            )
        }

        companion object {
            fun timeout(
                durationMillis: Double,
                outcome: String,
                renderId: Long? = null,
                webViewInstanceId: Long? = null,
            ): GraphMeasurement =
                GraphMeasurement(
                    renderId = renderId,
                    webViewInstanceId = webViewInstanceId,
                    durationMillis = durationMillis,
                    domNodeCount = null,
                    domEdgeCount = null,
                    tickCount = null,
                    success = false,
                    outcome = outcome,
                )
        }
    }

    private data class GraphStateScenario(
        val name: String,
        val graph: GraphUiModel,
        val expectedText: String,
    )

    private companion object {
        const val GRAPH_FILE = "graph_measurements.csv"
        const val GRAPH_STATE_FILE = "graph_state_measurements.csv"
        const val MAX_GRAPH_NODES = 50
        const val MAX_PAIR_COUNT = 100
        const val DEFAULT_WARMUP_PAIRS = 1
        const val DEFAULT_MEASURED_PAIRS = 5
        const val STATE_WARMUPS = 3
        const val STATE_ITERATIONS = 30
        const val RENDER_TIMEOUT_MILLIS = 10_000L
        const val STATE_TIMEOUT_MILLIS = 3_000L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        const val BOOTSTRAP_MARKER = "graph-render-bootstrap"
        const val SESSION_ID_ARGUMENT = "e4SessionId"
        const val NODE_ORDER_ARGUMENT = "e4GraphNodeOrder"
        const val WARMUP_PAIRS_ARGUMENT = "e4GraphWarmupPairs"
        const val MEASURED_PAIRS_ARGUMENT = "e4GraphMeasuredPairs"
        const val PHASE_NEW_WEB_VIEW = "new_webview_instance"
        const val PHASE_REUSED_WEB_VIEW = "reused_webview"
        val NODE_COUNTS = listOf(1, 12, 25, 50)
        val GRAPH_HEADER =
            listOf(
                "track",
                "scenario",
                "session_id",
                "node_order_index",
                "pair_index",
                "node_count",
                "edge_count",
                "phase",
                "render_id",
                "webview_instance_id",
                "duration_ms",
                "dom_node_count",
                "dom_edge_count",
                "tick_count",
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
