@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.graph

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
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
        Text(
            text = stringResource(R.string.graph_direction_legend),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
