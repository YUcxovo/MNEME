@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphUiModel

@Composable
internal fun GraphHeader(graph: GraphUiModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = stringResource(R.string.graph_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text =
                pluralStringResource(
                    R.plurals.graph_local_paper_count,
                    graph.nodes.size,
                    graph.nodes.size,
                ) + " - " +
                    pluralStringResource(
                        R.plurals.graph_directed_citation_count,
                        graph.edges.size,
                        graph.edges.size,
                    ),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        GraphStatusPill(graph.algorithmStatus)
        Text(
            text = stringResource(R.string.graph_direction_legend),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        graph.graphVersion?.takeIf(String::isNotBlank)?.let { version ->
            Text(
                text = stringResource(R.string.graph_version, version),
                modifier = Modifier.testTag("graph-version"),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun GraphStatusPill(status: GraphAlgorithmUiStatus) {
    val isReady = status == GraphAlgorithmUiStatus.READY
    Surface(
        modifier = Modifier.testTag("graph-algorithm-status"),
        color =
            if (isReady) {
                MaterialTheme.colorScheme.tertiaryContainer
            } else {
                MaterialTheme.colorScheme.surface
            },
        contentColor =
            if (isReady) {
                MaterialTheme.colorScheme.onTertiaryContainer
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
        shape = MaterialTheme.shapes.extraLarge,
        border =
            if (isReady) {
                null
            } else {
                BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
            },
    ) {
        Text(
            text =
                stringResource(
                    if (isReady) {
                        R.string.graph_status_ready
                    } else {
                        R.string.graph_status_fallback
                    },
                ),
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelMedium,
        )
    }
}
