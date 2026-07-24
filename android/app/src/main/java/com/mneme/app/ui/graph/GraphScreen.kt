@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.component.ContentSourceNotice
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.model.GraphUiModel

@Composable
fun GraphScreen(
    graph: GraphUiModel,
    onRetry: () -> Unit,
    onOpenPaper: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (graph.nodes.isEmpty()) {
        EmptyGraphScreen(onRetry = onRetry, modifier = modifier)
        return
    }
    var selectedPaperId by rememberSaveable(graph.centerId) {
        mutableStateOf<String?>(graph.centerId)
    }
    LaunchedEffect(graph.nodes) {
        if (graph.nodes.none { node -> node.id == selectedPaperId }) {
            selectedPaperId = graph.centerId
        }
    }
    GraphContent(
        graph = graph,
        selectedPaperId = selectedPaperId,
        onNodeSelected = { paperId -> selectedPaperId = paperId },
        onOpenPaper = onOpenPaper,
        modifier = modifier,
    )
}

@Composable
private fun GraphContent(
    graph: GraphUiModel,
    selectedPaperId: String?,
    onNodeSelected: (String) -> Unit,
    onOpenPaper: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val selectedNode = graph.nodes.firstOrNull { node -> node.id == selectedPaperId }
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("graph-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            GraphHeader(graph)
        }
        item {
            ContentSourceNotice(
                disclosure = graph.disclosure,
                testTag = "graph-source-notice",
            )
        }
        item {
            CitationGraphWebView(
                graph = graph,
                onNodeSelected = onNodeSelected,
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .height(460.dp)
                        .testTag("citation-graph-webview"),
            )
        }
        item {
            Text(
                text = stringResource(R.string.graph_gesture_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            MnemeSectionLabel(text = stringResource(R.string.graph_accessible_nodes))
        }
        item {
            GraphNodeChooser(
                nodes = graph.nodes,
                selectedPaperId = selectedPaperId,
                onNodeSelected = onNodeSelected,
            )
        }
        selectedNode?.let { node ->
            item {
                SelectedPaperCard(
                    node = node,
                    isCenter = node.id == graph.centerId,
                    onOpenPaper = { onOpenPaper(node.id) },
                )
            }
        }
    }
}
