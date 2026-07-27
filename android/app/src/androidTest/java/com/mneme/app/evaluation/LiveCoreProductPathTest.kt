@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import android.util.Base64
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.ui.GraphUiState
import com.mneme.app.ui.MnemeApp
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.OnboardingUiState
import com.mneme.app.ui.PaperDetailUiState
import com.mneme.app.ui.QaUiState
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.theme.MnemeTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LiveCoreProductPathTest {
    @get:Rule
    val composeRule = createComposeRule()

    private var failures = 0

    @Test
    fun fixedSeedAndQuestion_completeLiveUiAndRepeatedRepositoryPaths() {
        val arguments = InstrumentationRegistry.getArguments()
        val baseUrl = arguments.getString(BASE_URL_ARGUMENT)
        val token = arguments.getString(TOKEN_ARGUMENT)
        val seed = arguments.getString(SEED_ARGUMENT) ?: DEFAULT_SEED
        val encodedQuestion = arguments.getString(QUESTION_BASE64_ARGUMENT)
        val question =
            encodedQuestion?.let {
                String(Base64.decode(it, Base64.DEFAULT), Charsets.UTF_8)
            } ?: DEFAULT_QUESTION
        assumeTrue(
            "Live-core evaluation requires explicit backend URL and token arguments.",
            !baseUrl.isNullOrBlank() && !token.isNullOrBlank(),
        )

        LiveCoreMeasurementFiles.resetCsv(RESULT_FILE, RESULT_HEADER)
        val remote = MnemeApiClient.create(requireNotNull(baseUrl), requireNotNull(token))
        runLiveUiPath(remote, seed, question)
        runBlocking {
            repeat(REPOSITORY_ITERATIONS) { index ->
                runRepositoryPath(remote, seed, question, index + 1)
            }
        }
        assertEquals("Every retained live-core stage must meet its criterion.", 0, failures)
    }

    private fun runLiveUiPath(
        remote: com.mneme.app.data.network.MnemeRemoteDataSource,
        seed: String,
        question: String,
    ) {
        val database = createDatabase()
        try {
            val repository = repository(remote, database)
            val viewModel = MnemeViewModel(repository)
            val openedUrls = mutableListOf<String>()
            composeRule.setContent {
                MnemeTheme {
                    MnemeApp(
                        viewModel = viewModel,
                        onOpenSource = openedUrls::add,
                    )
                }
            }
            composeRule.waitUntil(UI_STATE_TIMEOUT_MILLIS) {
                viewModel.onboardingState.value is OnboardingUiState.AwaitingSeed
            }

            val seedStartedAt = now()
            composeRule.onNodeWithTag("seed-paper-input").performTextInput(seed)
            composeRule.onNodeWithTag("seed-paper-submit").performClick()
            composeRule.waitUntil(LIVE_STAGE_TIMEOUT_MILLIS) {
                viewModel.homeState.value is HomeUiState.Content &&
                    viewModel.onboardingState.value is OnboardingUiState.Ready
            }
            val briefing = (viewModel.homeState.value as HomeUiState.Content).briefing
            val selectedPaperId = briefing.papers.first().id
            waitForTag("content-source-notice")
            record(
                track = LIVE_UI_TRACK,
                scenario = "seed_to_five_paper_briefing",
                iteration = 1,
                startedAt = seedStartedAt,
                success =
                    briefing.papers.size == EXPECTED_PAPER_COUNT &&
                        briefing.disclosure.origin == ContentOrigin.LIVE_BACKEND,
                outcome = "briefing_rendered",
                seed = seed,
                selectedPaperId = selectedPaperId,
                paperCount = briefing.papers.size,
                contentOrigin = briefing.disclosure.origin.name,
            )
            captureComposeScreenshot("live_ui_briefing.png")

            val paperStartedAt = now()
            composeRule.onAllNodes(hasScrollAction()).onFirst().performScrollToNode(
                hasTestTag("paper-card-$selectedPaperId"),
            )
            composeRule.onNodeWithTag("paper-card-$selectedPaperId").performClick()
            composeRule.waitUntil(LIVE_STAGE_TIMEOUT_MILLIS) {
                viewModel.paperState.value is PaperDetailUiState.Content
            }
            val paper = (viewModel.paperState.value as PaperDetailUiState.Content).paper
            waitForTag("basic-summary")
            recordPaper(
                track = LIVE_UI_TRACK,
                scenario = "paper_and_summary",
                iteration = 1,
                startedAt = paperStartedAt,
                seed = seed,
                paper = paper,
            )
            captureComposeScreenshot("live_ui_paper.png")

            val paperSourceStartedAt = now()
            composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
                hasTestTag("paper-source-card"),
            )
            composeRule.onAllNodesWithText(OPEN_SOURCE_LABEL).onFirst().performClick()
            record(
                track = LIVE_UI_TRACK,
                scenario = "open_paper_source",
                iteration = 1,
                startedAt = paperSourceStartedAt,
                success = openedUrls.lastOrNull() == paper.source.url,
                outcome = "source_callback",
                seed = seed,
                selectedPaperId = selectedPaperId,
                selectedArxivId = paper.source.url.arxivId(),
                sourceCount = 1,
                contentOrigin = paper.disclosure.origin.name,
            )

            val qaStartedAt = now()
            composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
                hasTestTag("ask-question-action"),
            )
            composeRule.onNodeWithTag("ask-question-action").performClick()
            composeRule.onNodeWithTag("qa-question-input").performTextInput(question)
            composeRule.onNodeWithTag("qa-submit-question").performClick()
            composeRule.waitUntil(LIVE_STAGE_TIMEOUT_MILLIS) {
                viewModel.qaState.value is QaUiState.Content ||
                    viewModel.qaState.value is QaUiState.Error
            }
            val qa = (viewModel.qaState.value as? QaUiState.Content)?.qa
            recordQa(
                track = LIVE_UI_TRACK,
                scenario = "free_question_and_sources",
                iteration = 1,
                startedAt = qaStartedAt,
                seed = seed,
                selectedPaperId = selectedPaperId,
                qa = qa,
            )
            if (!qa?.sources.isNullOrEmpty()) {
                val qaSourceStartedAt = now()
                composeRule.onNodeWithTag("qa-screen").performScrollToNode(
                    hasTestTag("qa-source-card"),
                )
                waitForTag("qa-source-card")
                captureComposeScreenshot("live_ui_qa.png")
                composeRule.onAllNodesWithText(OPEN_SOURCE_LABEL).onFirst().performClick()
                record(
                    track = LIVE_UI_TRACK,
                    scenario = "open_qa_source",
                    iteration = 1,
                    startedAt = qaSourceStartedAt,
                    success = openedUrls.lastOrNull() in qa!!.sources.map { source -> source.url },
                    outcome = "citation_source_callback",
                    seed = seed,
                    selectedPaperId = selectedPaperId,
                    selectedArxivId = paper.source.url.arxivId(),
                    sourceCount = qa.sources.size,
                    sourceMatchStatus = qa.sourceMatchStatus.name,
                    contentOrigin = qa.disclosure.origin.name,
                )
            } else {
                waitForTag("qa-screen")
                captureComposeScreenshot("live_ui_qa.png")
            }

            composeRule.onNodeWithTag("navigate-back").performClick()
            val graphStartedAt = now()
            composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
                hasTestTag("explore-graph-action"),
            )
            composeRule.onNodeWithTag("explore-graph-action").performClick()
            composeRule.waitUntil(LIVE_STAGE_TIMEOUT_MILLIS) {
                viewModel.graphState.value is GraphUiState.Content ||
                    viewModel.graphState.value is GraphUiState.Error
            }
            val graph = (viewModel.graphState.value as? GraphUiState.Content)?.graph
            waitForTag("graph-screen")
            recordGraph(
                track = LIVE_UI_TRACK,
                scenario = "citation_graph",
                iteration = 1,
                startedAt = graphStartedAt,
                seed = seed,
                selectedPaperId = selectedPaperId,
                graph = graph,
            )
            composeRule.onNodeWithTag("graph-screen").performScrollToNode(
                hasTestTag("citation-graph-webview"),
            )
            captureComposeScreenshot("live_ui_graph.png")

            val neighbor = graph?.nodes?.firstOrNull { node -> node.id != graph.centerId }
            val selectGraphPaperStartedAt = now()
            if (neighbor != null) {
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
                record(
                    track = LIVE_UI_TRACK,
                    scenario = "select_graph_neighbor",
                    iteration = 1,
                    startedAt = selectGraphPaperStartedAt,
                    success = selected,
                    outcome =
                        if (selected) {
                            "neighbor_selection_visible"
                        } else {
                            "neighbor_selection_not_visible"
                        },
                    seed = seed,
                    selectedPaperId = neighbor.id,
                    graphNodes = graph.nodes.size,
                    graphEdges = graph.edges.size,
                    graphStatus = graph.algorithmStatus.name,
                    contentOrigin = graph.disclosure.origin.name,
                )
                captureComposeScreenshot("live_ui_graph_neighbor_selected.png")
            } else {
                record(
                    track = LIVE_UI_TRACK,
                    scenario = "select_graph_neighbor",
                    iteration = 1,
                    startedAt = selectGraphPaperStartedAt,
                    success = false,
                    outcome = "no_neighbor_available",
                    seed = seed,
                    selectedPaperId = selectedPaperId,
                    graphNodes = graph?.nodes?.size,
                    graphEdges = graph?.edges?.size,
                    graphStatus = graph?.algorithmStatus?.name,
                    contentOrigin = graph?.disclosure?.origin?.name,
                )
            }

            val openGraphPaperStartedAt = now()
            if (neighbor != null) {
                composeRule.onNodeWithTag("graph-screen").performScrollToNode(
                    hasTestTag("open-selected-graph-paper"),
                )
                composeRule.onNodeWithTag("open-selected-graph-paper").performClick()
                composeRule.waitUntil(LIVE_STAGE_TIMEOUT_MILLIS) {
                    val state = viewModel.paperState.value
                    state is PaperDetailUiState.Content && state.paper.paper.id == neighbor.id
                }
                record(
                    track = LIVE_UI_TRACK,
                    scenario = "open_selected_graph_paper",
                    iteration = 1,
                    startedAt = openGraphPaperStartedAt,
                    success =
                        (viewModel.paperState.value as? PaperDetailUiState.Content)
                            ?.paper
                            ?.paper
                            ?.id == neighbor.id,
                    outcome = "neighbor_paper_detail_rendered",
                    seed = seed,
                    selectedPaperId = neighbor.id,
                    graphNodes = graph.nodes.size,
                    graphEdges = graph.edges.size,
                    graphStatus = graph.algorithmStatus.name,
                    contentOrigin = graph.disclosure.origin.name,
                )
            } else {
                record(
                    track = LIVE_UI_TRACK,
                    scenario = "open_selected_graph_paper",
                    iteration = 1,
                    startedAt = openGraphPaperStartedAt,
                    success = false,
                    outcome = "no_graph_neighbor_available",
                    seed = seed,
                    selectedPaperId = selectedPaperId,
                    selectedArxivId = paper.source.url.arxivId(),
                    graphNodes = graph?.nodes?.size,
                    graphEdges = graph?.edges?.size,
                    graphStatus = graph?.algorithmStatus?.name,
                    contentOrigin = graph?.disclosure?.origin?.name,
                )
            }
        } finally {
            database.close()
        }
    }

    private fun waitForTag(tag: String) {
        composeRule.waitUntil(UI_STATE_TIMEOUT_MILLIS) {
            composeRule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.waitForIdle()
    }

    private fun captureComposeScreenshot(fileName: String) {
        composeRule.waitForIdle()
        LiveCoreMeasurementFiles.captureScreenshot(
            fileName,
            composeRule.onRoot().captureToImage().asAndroidBitmap(),
        )
    }

    private suspend fun runRepositoryPath(
        remote: com.mneme.app.data.network.MnemeRemoteDataSource,
        seed: String,
        question: String,
        iteration: Int,
    ) {
        val database = createDatabase()
        try {
            val repository = repository(remote, database)
            val seedStartedAt = now()
            val briefing = repository.initializeFromSeed(seed)
            val selectedPaperId = briefing.papers.first().id
            recordBriefing(
                scenario = "seed_to_five_paper_briefing",
                iteration = iteration,
                startedAt = seedStartedAt,
                seed = seed,
                briefing = briefing,
                selectedPaperId = selectedPaperId,
                expectedOrigin = ContentOrigin.LIVE_BACKEND,
            )

            val cacheStartedAt = now()
            val restored = repository.restoreBriefing()
            recordBriefing(
                scenario = "cached_briefing_restore",
                iteration = iteration,
                startedAt = cacheStartedAt,
                seed = seed,
                briefing = restored,
                selectedPaperId = selectedPaperId,
                expectedOrigin = ContentOrigin.CACHED_BACKEND,
            )

            val paperStartedAt = now()
            val loadedPaper = awaitPaper(repository, selectedPaperId)
            recordPaper(
                track = LIVE_REPOSITORY_TRACK,
                scenario = "paper_and_summary",
                iteration = iteration,
                startedAt = paperStartedAt,
                seed = seed,
                paper = loadedPaper.paper,
                pollCount = loadedPaper.pollCount,
            )

            val qaStartedAt = now()
            val qa = repository.askQuestion(selectedPaperId, question)
            recordQa(
                track = LIVE_REPOSITORY_TRACK,
                scenario = "free_question_and_sources",
                iteration = iteration,
                startedAt = qaStartedAt,
                seed = seed,
                selectedPaperId = selectedPaperId,
                qa = qa,
            )

            val graphStartedAt = now()
            val graph = repository.loadGraph(selectedPaperId)
            recordGraph(
                track = LIVE_REPOSITORY_TRACK,
                scenario = "citation_graph",
                iteration = iteration,
                startedAt = graphStartedAt,
                seed = seed,
                selectedPaperId = selectedPaperId,
                graph = graph,
            )

            val graphPaperId =
                graph.nodes.firstOrNull { node -> node.id != graph.centerId }?.id
                    ?: graph.centerId
            val graphPaperStartedAt = now()
            val graphPaper = awaitPaper(repository, graphPaperId)
            val selectedGraphSourceUrl = graphPaper.paper.source.url
            val selectedGraphArxivId = selectedGraphSourceUrl.arxivId()
            record(
                track = LIVE_REPOSITORY_TRACK,
                scenario = "open_selected_graph_paper",
                iteration = iteration,
                startedAt = graphPaperStartedAt,
                success = graphPaper.paper.paper.id == graphPaperId,
                outcome =
                    if (graphPaperId == graph.centerId) {
                        "center_paper_ready"
                    } else {
                        "neighbor_paper_ready"
                    },
                seed = seed,
                selectedPaperId = graphPaperId,
                selectedArxivId = selectedGraphArxivId,
                graphNodes = graph.nodes.size,
                graphEdges = graph.edges.size,
                graphStatus = graph.algorithmStatus.name,
                contentOrigin = graphPaper.paper.disclosure.origin.name,
                pollCount = graphPaper.pollCount,
            )
        } catch (error: Exception) {
            record(
                track = LIVE_REPOSITORY_TRACK,
                scenario = "iteration_completion",
                iteration = iteration,
                startedAt = now(),
                success = false,
                outcome = error::class.java.simpleName,
                seed = seed,
            )
        } finally {
            database.close()
        }
    }

    private fun recordBriefing(
        scenario: String,
        iteration: Int,
        startedAt: Long,
        seed: String,
        briefing: BriefingUiModel?,
        selectedPaperId: String,
        expectedOrigin: ContentOrigin,
    ) {
        record(
            track = LIVE_REPOSITORY_TRACK,
            scenario = scenario,
            iteration = iteration,
            startedAt = startedAt,
            success =
                briefing?.papers?.size == EXPECTED_PAPER_COUNT &&
                    briefing.disclosure.origin == expectedOrigin,
            outcome = "briefing_ui_model_returned",
            seed = seed,
            selectedPaperId = selectedPaperId,
            paperCount = briefing?.papers?.size,
            contentOrigin = briefing?.disclosure?.origin?.name,
        )
    }

    private fun recordPaper(
        track: String,
        scenario: String,
        iteration: Int,
        startedAt: Long,
        seed: String,
        paper: PaperDetailUiModel,
        pollCount: Int = 0,
    ) {
        record(
            track = track,
            scenario = scenario,
            iteration = iteration,
            startedAt = startedAt,
            success =
                paper.paper.summary.isNotBlank() &&
                    paper.abstractText.isNotBlank() &&
                    paper.source.url.startsWith(ARXIV_ABS_PREFIX) &&
                    paper.disclosure.origin == ContentOrigin.LIVE_BACKEND,
            outcome = "paper_detail_ui_model_returned",
            seed = seed,
            selectedPaperId = paper.paper.id,
            selectedArxivId = paper.source.url.arxivId(),
            sourceCount = 1,
            sourceMatchStatus = paper.sourceMatchStatus.name,
            contentOrigin = paper.disclosure.origin.name,
            pollCount = pollCount,
        )
    }

    private fun recordQa(
        track: String,
        scenario: String,
        iteration: Int,
        startedAt: Long,
        seed: String,
        selectedPaperId: String,
        qa: QaUiModel?,
    ) {
        val validSources =
            qa?.sources?.isNotEmpty() == true &&
                qa.sources.all { source -> source.url.startsWith(ARXIV_ABS_PREFIX) }
        record(
            track = track,
            scenario = scenario,
            iteration = iteration,
            startedAt = startedAt,
            success =
                qa?.answer?.isNotBlank() == true &&
                    qa.disclosure.origin == ContentOrigin.LIVE_BACKEND,
            outcome =
                when {
                    qa == null -> "qa_error"
                    !validSources -> "answer_without_citation_source"
                    else -> "answer_with_citation_source"
                },
            seed = seed,
            selectedPaperId = selectedPaperId,
            answerChars = qa?.answer?.length,
            sourceCount = qa?.sources?.size,
            sourceMatchStatus = qa?.sourceMatchStatus?.name,
            contentOrigin = qa?.disclosure?.origin?.name,
        )
    }

    private fun recordGraph(
        track: String,
        scenario: String,
        iteration: Int,
        startedAt: Long,
        seed: String,
        selectedPaperId: String,
        graph: GraphUiModel?,
    ) {
        val valid =
            graph != null &&
                graph.centerId == selectedPaperId &&
                graph.nodes.size >= MIN_GRAPH_NODES &&
                graph.edges.size >= MIN_GRAPH_EDGES &&
                graph.nodes.size <= GRAPH_NODE_LIMIT &&
                graph.disclosure.origin == ContentOrigin.LIVE_BACKEND
        record(
            track = track,
            scenario = scenario,
            iteration = iteration,
            startedAt = startedAt,
            success = valid,
            outcome =
                when {
                    graph == null -> "graph_error"
                    graph.nodes.size < MIN_GRAPH_NODES -> "insufficient_graph_nodes"
                    graph.edges.size < MIN_GRAPH_EDGES -> "insufficient_graph_edges"
                    else -> "multi_node_graph"
                },
            seed = seed,
            selectedPaperId = selectedPaperId,
            graphNodes = graph?.nodes?.size,
            graphEdges = graph?.edges?.size,
            graphStatus = graph?.algorithmStatus?.name,
            contentOrigin = graph?.disclosure?.origin?.name,
        )
    }

    private fun record(
        track: String,
        scenario: String,
        iteration: Int,
        startedAt: Long,
        success: Boolean,
        outcome: String,
        seed: String,
        selectedPaperId: String? = null,
        selectedArxivId: String? = null,
        paperCount: Int? = null,
        answerChars: Int? = null,
        sourceCount: Int? = null,
        sourceMatchStatus: String? = null,
        graphNodes: Int? = null,
        graphEdges: Int? = null,
        graphStatus: String? = null,
        contentOrigin: String? = null,
        pollCount: Int? = null,
    ) {
        LiveCoreMeasurementFiles.appendCsv(
            RESULT_FILE,
            listOf(
                track,
                scenario,
                iteration,
                elapsedMillis(startedAt),
                success,
                outcome,
                seed,
                selectedPaperId,
                selectedArxivId,
                paperCount,
                answerChars,
                sourceCount,
                sourceMatchStatus,
                graphNodes,
                graphEdges,
                graphStatus,
                contentOrigin,
                pollCount,
            ),
        )
        if (!success) {
            failures += 1
        }
    }

    private suspend fun awaitPaper(
        repository: SkeletalDataRepository,
        paperId: String,
    ): LoadedPaper {
        var result = repository.loadPaper(paperId)
        var pollCount = 0
        while (result is PaperContentResult.Processing) {
            check(pollCount < MAX_JOB_POLLS) { "Paper preparation exceeded the polling limit." }
            delay(JOB_POLL_INTERVAL_MILLIS)
            pollCount += 1
            result = repository.refreshPaper(result.paperId, result.jobId)
        }
        return LoadedPaper(
            paper = (result as PaperContentResult.Ready).paper,
            pollCount = pollCount,
        )
    }

    private fun repository(
        remote: com.mneme.app.data.network.MnemeRemoteDataSource,
        database: MnemeDatabase,
    ): NetworkSkeletalDataRepository =
        NetworkSkeletalDataRepository(
            remote = remote,
            cache = RoomSkeletalCache(database, MnemeApiClient.json),
        )

    private fun createDatabase(): MnemeDatabase {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Room
            .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    private fun now(): Long = SystemClock.elapsedRealtimeNanos()

    private fun elapsedMillis(startedAt: Long): Double = (SystemClock.elapsedRealtimeNanos() - startedAt) / NANOS_PER_MILLISECOND

    private fun String.arxivId(): String? = takeIf { startsWith(ARXIV_ABS_PREFIX) }?.removePrefix(ARXIV_ABS_PREFIX)

    private data class LoadedPaper(
        val paper: PaperDetailUiModel,
        val pollCount: Int,
    )

    private companion object {
        const val BASE_URL_ARGUMENT = "liveCoreBaseUrl"
        const val TOKEN_ARGUMENT = "liveCoreToken"
        const val SEED_ARGUMENT = "liveCoreSeed"
        const val QUESTION_BASE64_ARGUMENT = "liveCoreQuestionBase64"
        const val DEFAULT_SEED = "1706.03762"
        const val DEFAULT_QUESTION =
            "What problem does this paper address, and what method does it propose?"
        const val OPEN_SOURCE_LABEL = "Open source paper"
        const val RESULT_FILE = "live_core_path.csv"
        const val LIVE_UI_TRACK = "live_ui"
        const val LIVE_REPOSITORY_TRACK = "live_repository"
        const val EXPECTED_PAPER_COUNT = 5
        const val REPOSITORY_ITERATIONS = 5
        const val MIN_GRAPH_NODES = 2
        const val MIN_GRAPH_EDGES = 1
        const val GRAPH_NODE_LIMIT = 50
        const val MAX_JOB_POLLS = 900
        const val JOB_POLL_INTERVAL_MILLIS = 1_000L
        const val UI_STATE_TIMEOUT_MILLIS = 30_000L
        const val LIVE_STAGE_TIMEOUT_MILLIS = 15 * 60 * 1_000L
        const val NANOS_PER_MILLISECOND = 1_000_000.0
        const val ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"
        val RESULT_HEADER =
            listOf(
                "track",
                "scenario",
                "iteration",
                "duration_ms",
                "success",
                "outcome",
                "seed_arxiv_id",
                "selected_paper_id",
                "selected_arxiv_id",
                "paper_count",
                "answer_chars",
                "source_count",
                "source_match_status",
                "graph_nodes",
                "graph_edges",
                "graph_status",
                "content_origin",
                "poll_count",
            )
    }
}
