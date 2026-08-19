@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import android.annotation.SuppressLint
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.mneme.app.ui.model.GraphUiModel
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

// JavascriptInterface is a lint false positive through Compose remember; the bridge
// method is annotated directly and covered by the API 34 bridge test.
@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
internal fun CitationGraphWebView(
    graph: GraphUiModel,
    onNodeSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
    onWebViewCreated: (WebView) -> Unit = {},
    onRendererReady: () -> Unit = {},
) {
    val selectionCallback = rememberUpdatedState(onNodeSelected)
    val rendererReadyCallback = rememberUpdatedState(onRendererReady)
    val payload = remember(graph) { graph.toRenderPayload() }
    val bridge: GraphJavaScriptBridge =
        remember {
            GraphJavaScriptBridge { paperId ->
                selectionCallback.value(paperId)
            }
        }
    var pageReady by remember { mutableStateOf(false) }
    SideEffect {
        bridge.updatePaperIds(graph.nodes.mapTo(mutableSetOf()) { node -> node.id })
    }

    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.allowContentAccess = false
                settings.javaScriptCanOpenWindowsAutomatically = false
                settings.domStorageEnabled = false
                addJavascriptInterface(bridge, BRIDGE_NAME)
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
                                pageReady = true
                                render(payload)
                                rendererReadyCallback.value()
                            }
                        }
                    }
                loadUrl(GRAPH_ASSET_URL)
                onWebViewCreated(this)
            }
        },
        update = { webView ->
            if (pageReady) {
                webView.render(payload)
            }
        },
        onRelease = { webView ->
            webView.removeJavascriptInterface(BRIDGE_NAME)
            webView.stopLoading()
            webView.destroy()
        },
    )
}

private class GraphJavaScriptBridge(
    private val onNodeSelected: (String) -> Unit,
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
}

private fun WebView.render(payload: GraphRenderPayload) {
    val graphJson = Json.encodeToString(payload)
    evaluateJavascript(
        "if (window.MnemeGraph) { window.MnemeGraph.render($graphJson); }",
        null,
    )
}

private fun GraphUiModel.toRenderPayload(): GraphRenderPayload =
    GraphRenderPayload(
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

private const val BRIDGE_NAME = "MnemeGraphBridge"
private const val GRAPH_ASSET_URL = "file:///android_asset/citation_graph.html"
