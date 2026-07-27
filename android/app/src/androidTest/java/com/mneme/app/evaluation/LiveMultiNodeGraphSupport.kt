package com.mneme.app.evaluation

import android.content.Context
import android.os.SystemClock
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import kotlinx.coroutines.delay

internal class LiveGraphRecorder {
    var failures: Int = 0
        private set

    fun record(
        track: String,
        scenario: String,
        iteration: Int,
        startedAt: Long,
        success: Boolean,
        outcome: String,
        graphArxivId: String,
        centerPaperId: String,
        graph: GraphUiModel,
        selectedPaperId: String? = null,
        selectedArxivId: String? = null,
    ) {
        LiveCoreMeasurementFiles.appendCsv(
            LIVE_GRAPH_RESULT_FILE,
            listOf(
                track,
                scenario,
                iteration,
                liveGraphElapsedMillis(startedAt),
                success,
                outcome,
                graphArxivId,
                centerPaperId,
                selectedPaperId,
                selectedArxivId,
                graph.nodes.size,
                graph.edges.size,
                graph.algorithmStatus.name,
                graph.disclosure.origin.name,
            ),
        )
        if (!success) {
            failures += 1
        }
    }
}

internal fun GraphUiModel.meetsLiveGraphCriterion(centerPaperId: String): Boolean =
    centerId == centerPaperId &&
        nodes.size >= LIVE_GRAPH_MIN_NODES &&
        edges.size >= LIVE_GRAPH_MIN_EDGES &&
        nodes.any { node -> node.id == centerId } &&
        disclosure.origin == ContentOrigin.LIVE_BACKEND

internal suspend fun awaitLiveGraphPaper(
    repository: NetworkSkeletalDataRepository,
    paperId: String,
): PaperDetailUiModel {
    var result = repository.loadPaper(paperId)
    var pollCount = 0
    while (result is PaperContentResult.Processing) {
        check(pollCount < LIVE_GRAPH_MAX_JOB_POLLS) {
            "Paper preparation exceeded the polling limit."
        }
        delay(LIVE_GRAPH_JOB_POLL_MILLIS)
        pollCount += 1
        result = repository.refreshPaper(result.paperId, result.jobId)
    }
    return (result as PaperContentResult.Ready).paper
}

internal fun createLiveGraphDatabase(): MnemeDatabase {
    val context = ApplicationProvider.getApplicationContext<Context>()
    return Room
        .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
        .allowMainThreadQueries()
        .build()
}

internal fun liveGraphNow(): Long = SystemClock.elapsedRealtimeNanos()

private fun liveGraphElapsedMillis(startedAt: Long): Double =
    (SystemClock.elapsedRealtimeNanos() - startedAt) / LIVE_GRAPH_NANOS_PER_MILLISECOND

internal fun String.toArxivId(): String? =
    takeIf { startsWith(LIVE_GRAPH_ARXIV_ABS_PREFIX) }
        ?.removePrefix(LIVE_GRAPH_ARXIV_ABS_PREFIX)

internal const val LIVE_GRAPH_RESULT_FILE = "live_multi_node_graph.csv"
internal const val LIVE_GRAPH_REPOSITORY_TRACK = "live_graph_repository"
internal const val LIVE_GRAPH_UI_TRACK = "live_graph_ui"
internal const val LIVE_GRAPH_REPOSITORY_ITERATIONS = 5
internal const val LIVE_GRAPH_PAPER_LOOKUP_LIMIT = 100
internal const val LIVE_GRAPH_MIN_NODES = 5
internal const val LIVE_GRAPH_MIN_EDGES = 7
internal const val LIVE_GRAPH_MAX_JOB_POLLS = 900
internal const val LIVE_GRAPH_JOB_POLL_MILLIS = 1_000L
internal const val LIVE_GRAPH_UI_TIMEOUT_MILLIS = 30_000L
private const val LIVE_GRAPH_NANOS_PER_MILLISECOND = 1_000_000.0
private const val LIVE_GRAPH_ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"

internal val LIVE_GRAPH_RESULT_HEADER =
    listOf(
        "track",
        "scenario",
        "iteration",
        "duration_ms",
        "success",
        "outcome",
        "graph_arxiv_id",
        "center_paper_id",
        "selected_paper_id",
        "selected_arxiv_id",
        "graph_nodes",
        "graph_edges",
        "graph_status",
        "content_origin",
    )
