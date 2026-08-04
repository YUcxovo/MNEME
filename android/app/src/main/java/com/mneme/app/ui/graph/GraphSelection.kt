@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.model.GraphNodeUiModel

@Composable
internal fun graphNodeChooser(
    nodes: List<GraphNodeUiModel>,
    selectedPaperId: String?,
    onNodeSelected: (String) -> Unit,
) {
    LazyRow(
        modifier = Modifier.fillMaxWidth().testTag("graph-node-chooser"),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(end = 16.dp),
    ) {
        items(
            items = nodes,
            key = GraphNodeUiModel::id,
        ) { node ->
            FilterChip(
                selected = node.id == selectedPaperId,
                onClick = { onNodeSelected(node.id) },
                label = { Text(node.title, maxLines = 1) },
                modifier = Modifier.testTag("graph-node-${node.id}"),
                colors =
                    FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.secondaryContainer,
                    ),
            )
        }
    }
}

@Composable
internal fun selectedPaperCard(
    node: GraphNodeUiModel,
    isCenter: Boolean,
    onOpenPaper: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().testTag("selected-graph-paper"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.45f)),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text =
                    stringResource(
                        if (isCenter) {
                            R.string.graph_selected_center
                        } else {
                            R.string.graph_selected_paper
                        },
                    ),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = node.title,
                modifier = Modifier.testTag("selected-graph-paper-title"),
                style = MaterialTheme.typography.titleMedium,
            )
            node.category?.takeIf(String::isNotBlank)?.let { category ->
                Text(
                    text = category,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Button(
                onClick = onOpenPaper,
                modifier = Modifier.fillMaxWidth().testTag("open-selected-graph-paper"),
                shape = MaterialTheme.shapes.small,
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.OpenInNew,
                    contentDescription = null,
                )
                Text(
                    text = stringResource(R.string.graph_open_selected),
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        }
    }
}

@Composable
internal fun emptyGraphScreen(
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .fillMaxSize()
                .padding(24.dp)
                .testTag("graph-empty"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = stringResource(R.string.graph_empty_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = stringResource(R.string.graph_empty_body),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(
            onClick = onRetry,
            modifier = Modifier.testTag("graph-empty-retry"),
        ) {
            Text(stringResource(R.string.graph_retry))
        }
    }
}
