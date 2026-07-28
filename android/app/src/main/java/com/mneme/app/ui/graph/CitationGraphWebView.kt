@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import android.annotation.SuppressLint
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.mneme.app.ui.model.GraphUiModel
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.concurrent.atomic.AtomicLong

// JavascriptInterface is a lint false positive through Compose remember; the bridge
// method is annotated directly and covered by the API 34 bridge test.
@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Suppress("LongParameterList")
@Composable
internal fun CitationGraphWebView(
    graph: GraphUiModel,
    onNodeSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
    onWebViewCreated: (WebView) -> Unit = {},
    onRendererReady: () -> Unit = {},
    measurementObserver: GraphRenderMeasurementObserver? = null,
) {
    val selectionCallback = rememberUpdatedState(onNodeSelected)
    val rendererReadyCallback = rememberUpdatedState(onRendererReady)
    val measurementObserverState = rememberUpdatedState(measurementObserver)
    val payload = remember(graph) { graph.toRenderPayload() }
    val coordinator: GraphRenderCoordinator =
        remember {
            GraphRenderCoordinator(
                onNodeSelected = { paperId ->
                    selectionCallback.value(paperId)
                },
                onRenderSubmitted = { submission ->
                    measurementObserverState.value?.onRenderSubmitted(submission)
                },
                onVisualStateReady = { completion ->
                    measurementObserverState.value?.onVisualStateReady(completion)
                    rendererReadyCallback.value()
                },
            )
        }
    SideEffect {
        coordinator.updatePaperIds(graph.nodes.mapTo(mutableSetOf()) { node -> node.id })
    }

    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                coordinator.attach(this)
                settings.javaScriptEnabled = true
                settings.allowContentAccess = false
                settings.javaScriptCanOpenWindowsAutomatically = false
                settings.domStorageEnabled = false
                addJavascriptInterface(coordinator.bridge, BRIDGE_NAME)
                webViewClient =
                    object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView?,
                            request: WebResourceRequest?,
                        ): Boolean = request?.url?.toString() != GRAPH_ASSET_URL

                        override fun onPageFinished(
                            view: WebView,
                            url: String,
                        ) {
                            if (url == GRAPH_ASSET_URL) {
                                coordinator.onPageFinished(view)
                            }
                        }
                    }
                loadUrl(GRAPH_ASSET_URL)
                onWebViewCreated(this)
            }
        },
        update = { webView ->
            coordinator.updatePayload(webView, payload)
        },
        onRelease = { webView ->
            coordinator.detach(webView)
            webView.removeJavascriptInterface(BRIDGE_NAME)
            webView.stopLoading()
            webView.destroy()
        },
    )
}

internal interface GraphRenderMeasurementObserver {
    fun onRenderSubmitted(submission: GraphRenderSubmission)

    fun onVisualStateReady(completion: GraphRenderCompletion)
}

internal data class GraphRenderSubmission(
    val renderId: Long,
    val webViewInstanceId: Long,
    val requestTag: String?,
    val nodeCount: Int,
    val edgeCount: Int,
    val submittedAtNanos: Long,
)

internal data class GraphRenderCompletion(
    val renderId: Long,
    val webViewInstanceId: Long,
    val requestTag: String?,
    val nodeCount: Int,
    val edgeCount: Int,
    val tickCount: Int,
    val completedAtNanos: Long,
)

private class GraphRenderCoordinator(
    onNodeSelected: (String) -> Unit,
    private val onRenderSubmitted: (GraphRenderSubmission) -> Unit,
    private val onVisualStateReady: (GraphRenderCompletion) -> Unit,
) {
    val bridge =
        GraphJavaScriptBridge(
            onNodeSelected = onNodeSelected,
            onRenderFrameReady = ::onRenderFrameReady,
        )

    private var webView: WebView? = null
    private var webViewInstanceId: Long = 0
    private var pageReady = false
    private var pendingPayload: GraphRenderPayload? = null
    private var submittedPayload: GraphRenderPayload? = null
    private var activeRender: ActiveRender? = null

    fun attach(webView: WebView) {
        this.webView = webView
        webViewInstanceId = WEB_VIEW_IDS.incrementAndGet()
        pageReady = false
        pendingPayload = null
        submittedPayload = null
        activeRender = null
    }

    fun detach(webView: WebView) {
        if (this.webView !== webView) {
            return
        }
        this.webView = null
        pageReady = false
        pendingPayload = null
        submittedPayload = null
        activeRender = null
    }

    fun updatePaperIds(paperIds: Set<String>) {
        bridge.updatePaperIds(paperIds)
    }

    fun updatePayload(
        webView: WebView,
        payload: GraphRenderPayload,
    ) {
        if (this.webView !== webView) {
            return
        }
        pendingPayload = payload
        submitPendingPayload()
    }

    fun onPageFinished(webView: WebView) {
        if (this.webView !== webView) {
            return
        }
        pageReady = true
        submitPendingPayload()
    }

    private fun submitPendingPayload() {
        val currentWebView = webView
        val payload = pendingPayload
        if (currentWebView == null || payload == null) {
            return
        }
        if (!pageReady || payload == submittedPayload) {
            return
        }

        val renderId = RENDER_IDS.incrementAndGet()
        val submission =
            GraphRenderSubmission(
                renderId = renderId,
                webViewInstanceId = webViewInstanceId,
                requestTag = payload.graphVersion,
                nodeCount = payload.nodes.size,
                edgeCount = payload.edges.size,
                submittedAtNanos = SystemClock.elapsedRealtimeNanos(),
            )
        submittedPayload = payload
        activeRender =
            ActiveRender(
                submission = submission,
                webView = currentWebView,
            )
        onRenderSubmitted(submission)
        currentWebView.render(payload, renderId)
    }

    private fun onRenderFrameReady(
        renderId: Long,
        nodeCount: Int,
        edgeCount: Int,
        tickCount: Int,
    ) {
        val render = activeRender ?: return
        if (render.submission.renderId != renderId || webView !== render.webView) {
            return
        }
        render.webView.postVisualStateCallback(
            renderId,
            object : WebView.VisualStateCallback() {
                override fun onComplete(requestId: Long) {
                    val currentRender = activeRender ?: return
                    if (
                        currentRender.submission.renderId != requestId ||
                        currentRender.webView !== render.webView ||
                        webView !== render.webView
                    ) {
                        return
                    }
                    activeRender = null
                    onVisualStateReady(
                        GraphRenderCompletion(
                            renderId = requestId,
                            webViewInstanceId = currentRender.submission.webViewInstanceId,
                            requestTag = currentRender.submission.requestTag,
                            nodeCount = nodeCount,
                            edgeCount = edgeCount,
                            tickCount = tickCount,
                            completedAtNanos = SystemClock.elapsedRealtimeNanos(),
                        ),
                    )
                }
            },
        )
    }

    private data class ActiveRender(
        val submission: GraphRenderSubmission,
        val webView: WebView,
    )
}

private class GraphJavaScriptBridge(
    private val onNodeSelected: (String) -> Unit,
    private val onRenderFrameReady: (Long, Int, Int, Int) -> Unit,
) {
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var validPaperIds: Set<String> = emptySet()

    fun updatePaperIds(paperIds: Set<String>) {
        validPaperIds = paperIds
    }

    @JavascriptInterface
    fun selectNode(paperId: String) {
        if (paperId !in validPaperIds) {
            return
        }
        mainHandler.post { onNodeSelected(paperId) }
    }

    @JavascriptInterface
    fun renderFrameReady(
        renderId: String,
        nodeCount: Int,
        edgeCount: Int,
        tickCount: Int,
    ) {
        val parsedRenderId = renderId.toLongOrNull() ?: return
        mainHandler.post {
            onRenderFrameReady(
                parsedRenderId,
                nodeCount,
                edgeCount,
                tickCount,
            )
        }
    }
}

private fun WebView.render(
    payload: GraphRenderPayload,
    renderId: Long,
) {
    val graphJson = Json.encodeToString(payload)
    val renderIdJson = Json.encodeToString(renderId.toString())
    evaluateJavascript(
        "if (window.MnemeGraph) { window.MnemeGraph.render($graphJson, $renderIdJson); }",
        null,
    )
}

private fun GraphUiModel.toRenderPayload(): GraphRenderPayload =
    GraphRenderPayload(
        graphVersion = graphVersion,
        centerId = centerId,
        nodes =
            nodes.map { node ->
                GraphRenderNode(
                    id = node.id,
                    title = node.title,
                    category = node.category,
                    clusterId = node.clusterId,
                    rankScore = node.rankScore,
                )
            },
        edges =
            edges.map { edge ->
                GraphRenderEdge(
                    source = edge.source,
                    target = edge.target,
                    weight = edge.weight,
                )
            },
    )

@Serializable
private data class GraphRenderPayload(
    val graphVersion: String?,
    val centerId: String,
    val nodes: List<GraphRenderNode>,
    val edges: List<GraphRenderEdge>,
)

@Serializable
private data class GraphRenderNode(
    val id: String,
    val title: String,
    val category: String?,
    val clusterId: String?,
    val rankScore: Double?,
)

@Serializable
private data class GraphRenderEdge(
    val source: String,
    val target: String,
    val weight: Double?,
)

private val RENDER_IDS = AtomicLong()
private val WEB_VIEW_IDS = AtomicLong()
private const val BRIDGE_NAME = "MnemeGraphBridge"
private const val GRAPH_ASSET_URL = "file:///android_asset/citation_graph.html"
