@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
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

private data class GraphScreenState(
    val relation: GraphRelationFilter,
    val category: String?,
    val selectedPaperId: String?,
)

private data class GraphScreenActions(
    val changeRelation: (GraphRelationFilter) -> Unit,
    val changeCategory: (String?) -> Unit,
    val selectPaper: (String) -> Unit,
    val openPaper: (String) -> Unit,
    val exploreGraph: (String) -> Unit,
)

@Composable
fun graphScreen(
    graph: GraphUiModel,
    onRetry: () -> Unit,
    onOpenPaper: (String) -> Unit,
    onExploreGraph: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (graph.nodes.isEmpty() || graph.edges.isEmpty()) {
        emptyGraphScreen(onRetry, modifier)
        return
    }
    var relation by rememberSaveable(graph.centerId) {
        mutableStateOf(GraphRelationFilter.ALL)
    }
    var category by rememberSaveable(graph.centerId) {
        mutableStateOf<String?>(null)
    }
    val filteredGraph = graph.filteredCitationGraph(relation, category).toGraph(graph)
    var selectedPaperId by rememberSaveable(graph.centerId) {
        mutableStateOf(graph.centerId)
    }
    LaunchedEffect(filteredGraph.nodes) {
        if (filteredGraph.nodes.none { it.id == selectedPaperId }) {
            selectedPaperId = graph.centerId
        }
    }
    graphContent(
        originalGraph = graph,
        graph = filteredGraph,
        state = GraphScreenState(relation, category, selectedPaperId),
        actions =
            GraphScreenActions(
                changeRelation = { relation = it },
                changeCategory = { category = it },
                selectPaper = { selectedPaperId = it },
                openPaper = onOpenPaper,
                exploreGraph = onExploreGraph,
            ),
        modifier = modifier,
    )
}

private fun FilteredCitationGraph.toGraph(original: GraphUiModel): GraphUiModel =
    original.copy(
        nodes = nodes,
        edges = edges,
    )

@Composable
private fun graphContent(
    originalGraph: GraphUiModel,
    graph: GraphUiModel,
    state: GraphScreenState,
    actions: GraphScreenActions,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("graph-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { graphHeaderBlock(originalGraph, state, actions) }
        if (graph.nodes.size == 1) {
            item {
                Text(
                    text = stringResource(R.string.graph_filter_empty),
                    modifier = Modifier.testTag("graph-filter-empty"),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
        item {
            CitationGraphWebView(
                graph = graph,
                onNodeSelected = actions.selectPaper,
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
        item { MnemeSectionLabel(text = stringResource(R.string.graph_accessible_nodes)) }
        item {
            graphSelection(
                originalGraph = originalGraph,
                graph = graph,
                state = state,
                actions = actions,
            )
        }
    }
}

@Composable
private fun graphHeaderBlock(
    graph: GraphUiModel,
    state: GraphScreenState,
    actions: GraphScreenActions,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        GraphHeader(graph)
        ContentSourceNotice(
            disclosure = graph.disclosure,
            testTag = "graph-source-notice",
        )
        graphFilters(
            relation = state.relation,
            category = state.category,
            categories = graph.availableCategories(),
            onRelationChanged = actions.changeRelation,
            onCategoryChanged = actions.changeCategory,
        )
    }
}

@Composable
private fun graphSelection(
    originalGraph: GraphUiModel,
    graph: GraphUiModel,
    state: GraphScreenState,
    actions: GraphScreenActions,
) {
    graphNodeChooser(
        nodes = graph.nodes,
        selectedPaperId = state.selectedPaperId,
        onNodeSelected = actions.selectPaper,
    )
    graph.nodes.firstOrNull { it.id == state.selectedPaperId }?.let { node ->
        selectedPaperCard(
            node = node,
            isCenter = node.id == originalGraph.centerId,
            onOpenPaper = { actions.openPaper(node.id) },
            onExploreGraph = { actions.exploreGraph(node.id) },
        )
    }
}

@Composable
private fun graphFilters(
    relation: GraphRelationFilter,
    category: String?,
    categories: List<String>,
    onRelationChanged: (GraphRelationFilter) -> Unit,
    onCategoryChanged: (String?) -> Unit,
) {
    LazyRow(
        modifier = Modifier.fillMaxWidth().testTag("graph-filters"),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(GraphRelationFilter.entries) { filter ->
            FilterChip(
                selected = relation == filter,
                onClick = { onRelationChanged(filter) },
                label = {
                    Text(filter.name.lowercase().replaceFirstChar(Char::uppercase))
                },
                modifier = Modifier.testTag("graph-relation-${filter.name.lowercase()}"),
            )
        }
        items(categories) { filterCategory ->
            FilterChip(
                selected = category == filterCategory,
                onClick = {
                    onCategoryChanged(
                        if (category == filterCategory) {
                            null
                        } else {
                            filterCategory
                        },
                    )
                },
                label = { Text(filterCategory) },
                modifier = Modifier.testTag("graph-category-$filterCategory"),
            )
        }
    }
}
