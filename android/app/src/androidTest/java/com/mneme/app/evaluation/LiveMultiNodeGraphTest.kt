@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.ui.graph.GraphScreen
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.theme.MnemeTheme
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class LiveMultiNodeGraphTest {
    @get:Rule
    val composeRule = createComposeRule()

    private val recorder = LiveGraphRecorder()

    @Test
    fun storedRealCitationGraph_loadsRendersSelectsAndOpensNeighbor() {
        val arguments = InstrumentationRegistry.getArguments()
        val baseUrl = arguments.getString(BASE_URL_ARGUMENT)
        val token = arguments.getString(TOKEN_ARGUMENT)
        val graphArxivId = arguments.getString(GRAPH_ARXIV_ARGUMENT) ?: DEFAULT_GRAPH_ARXIV
        assumeTrue(
            "Live graph evaluation requires explicit backend URL and token arguments.",
            !baseUrl.isNullOrBlank() && !token.isNullOrBlank(),
        )

        LiveCoreMeasurementFiles.createCsv(LIVE_GRAPH_RESULT_FILE, LIVE_GRAPH_RESULT_HEADER)
        val remote = MnemeApiClient.create(requireNotNull(baseUrl), requireNotNull(token))
        val database = createLiveGraphDatabase()
        try {
            val repository =
                NetworkSkeletalDataRepository(
                    remote = remote,
                    cache = RoomSkeletalCache(database, MnemeApiClient.json),
                )
            val center =
                runBlocking {
                    remote
                        .listPapers(limit = LIVE_GRAPH_PAPER_LOOKUP_LIMIT)
                        .items
                        .single { paper -> paper.arxivId == graphArxivId }
                }
            val graphs = mutableListOf<GraphUiModel>()
            runBlocking {
                repeat(LIVE_GRAPH_REPOSITORY_ITERATIONS) { index ->
                    val startedAt = liveGraphNow()
                    val graph = repository.loadGraph(center.id)
                    graphs += graph
                    recorder.record(
                        track = LIVE_GRAPH_REPOSITORY_TRACK,
                        scenario = "multi_node_graph_load",
                        iteration = index + 1,
                        startedAt = startedAt,
                        success = graph.meetsLiveGraphCriterion(center.id),
                        outcome =
                            if (graph.meetsLiveGraphCriterion(center.id)) {
                                "real_multi_node_graph"
                            } else {
                                "insufficient_local_graph"
                            },
                        graphArxivId = graphArxivId,
                        centerPaperId = center.id,
                        graph = graph,
                    )
                }
            }

            val graph = graphs.last()
            val neighbor = requireNotNull(graph.nodes.firstOrNull { node -> node.id != graph.centerId })
            val openedPaperId = AtomicReference<String>()
            val renderStartedAt = liveGraphNow()
            composeRule.setContent {
                MnemeTheme {
                    GraphScreen(
                        graph = graph,
                        onRetry = {},
                        onOpenPaper = openedPaperId::set,
                    )
                }
            }
            val rendered =
                waitUntilOrFalse(LIVE_GRAPH_UI_TIMEOUT_MILLIS) {
                    composeRule.onAllNodesWithTag("graph-screen").fetchSemanticsNodes().isNotEmpty() &&
                        composeRule
                            .onAllNodesWithTag("citation-graph-webview")
                            .fetchSemanticsNodes()
                            .isNotEmpty()
                }
            recorder.record(
                track = LIVE_GRAPH_UI_TRACK,
                scenario = "multi_node_graph_render",
                iteration = 1,
                startedAt = renderStartedAt,
                success = rendered && graph.meetsLiveGraphCriterion(center.id),
                outcome = if (rendered) "graph_screen_visible" else "graph_screen_timeout",
                graphArxivId = graphArxivId,
                centerPaperId = center.id,
                graph = graph,
            )

            val selectionStartedAt = liveGraphNow()
            composeRule.onNodeWithTag("graph-screen").performScrollToNode(
                hasTestTag("graph-node-chooser"),
            )
            composeRule.onNodeWithTag("graph-node-chooser").performScrollToNode(
                hasTestTag("graph-node-${neighbor.id}"),
            )
            composeRule.onNodeWithTag("graph-node-${neighbor.id}").performClick()
            composeRule.onNodeWithTag("graph-screen").performScrollToNode(
                hasTestTag("selected-graph-paper-title"),
            )
            val selected =
                runCatching {
                    composeRule
                        .onNodeWithTag("selected-graph-paper-title")
                        .assertTextContains(neighbor.title)
                }.isSuccess
            recorder.record(
                track = LIVE_GRAPH_UI_TRACK,
                scenario = "select_real_neighbor",
                iteration = 1,
                startedAt = selectionStartedAt,
                success = selected,
                outcome = if (selected) "neighbor_selection_persisted" else "selection_not_visible",
                graphArxivId = graphArxivId,
                centerPaperId = center.id,
                selectedPaperId = neighbor.id,
                graph = graph,
            )
            composeRule.waitForIdle()
            LiveCoreMeasurementFiles.captureScreenshot(
                "live_ui_multi_node_graph.png",
                composeRule.onRoot().captureToImage().asAndroidBitmap(),
            )

            val openStartedAt = liveGraphNow()
            composeRule.onNodeWithTag("open-selected-graph-paper").performClick()
            val callbackReceived =
                waitUntilOrFalse(LIVE_GRAPH_UI_TIMEOUT_MILLIS) {
                    openedPaperId.get() == neighbor.id
                }
            val paper =
                if (callbackReceived) {
                    runBlocking { awaitLiveGraphPaper(repository, neighbor.id) }
                } else {
                    null
                }
            val openSucceeded =
                callbackReceived &&
                    paper?.paper?.id == neighbor.id &&
                    paper.disclosure.origin == ContentOrigin.LIVE_BACKEND
            recorder.record(
                track = LIVE_GRAPH_UI_TRACK,
                scenario = "open_real_neighbor",
                iteration = 1,
                startedAt = openStartedAt,
                success = openSucceeded,
                outcome = if (openSucceeded) "neighbor_detail_ready" else "neighbor_open_failed",
                graphArxivId = graphArxivId,
                centerPaperId = center.id,
                selectedPaperId = neighbor.id,
                selectedArxivId = paper?.source?.url?.toArxivId(),
                graph = graph,
            )
        } finally {
            database.close()
        }
        assertEquals(
            "Every live multi-node graph stage must meet its criterion.",
            0,
            recorder.failures,
        )
    }

    private fun waitUntilOrFalse(
        timeoutMillis: Long,
        condition: () -> Boolean,
    ): Boolean =
        runCatching {
            composeRule.waitUntil(timeoutMillis, condition)
            true
        }.getOrDefault(false)

    private companion object {
        const val BASE_URL_ARGUMENT = "liveCoreBaseUrl"
        const val TOKEN_ARGUMENT = "liveCoreToken"
        const val GRAPH_ARXIV_ARGUMENT = "liveCoreGraphArxiv"
        const val DEFAULT_GRAPH_ARXIV = "1706.03762"
    }
}
