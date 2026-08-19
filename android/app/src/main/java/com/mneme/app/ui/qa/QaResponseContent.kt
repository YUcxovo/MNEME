@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.qa

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.component.ContentSourceNotice
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.component.SourceMatchStatusPill
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceUiModel

internal fun LazyListScope.qaResponseItems(
    qa: QaUiModel,
    turnIndex: Int,
    onOpenSource: (String) -> Unit,
) {
    item { ContentSourceNotice(disclosure = qa.disclosure) }
    item {
        Box(modifier = Modifier.testTag("qa-answer-turn-$turnIndex")) {
            AnswerBubble(answer = qa.answer)
        }
    }
    item {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            MnemeSectionLabel(text = stringResource(R.string.qa_source))
            SourceMatchStatusPill(status = qa.sourceMatchStatus)
        }
    }
    if (qa.sources.isEmpty()) {
        item {
            Text(
                text = stringResource(R.string.qa_no_citations),
                modifier = Modifier.testTag("qa-no-citations"),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    } else {
        items(
            items = qa.sources,
            key = { source -> "$turnIndex-${source.url}-${source.location}" },
        ) { source ->
            QaSourceCard(source = source, onOpenSource = onOpenSource)
        }
    }
}

@Composable
private fun AnswerBubble(
    answer: String,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("qa-answer"),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
            ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = RoundedCornerShape(6.dp, 18.dp, 18.dp, 18.dp),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.qa_answer),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = answer,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun QaSourceCard(
    source: SourceUiModel,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("qa-source-card"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.42f)),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.source_location_format, source.location),
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
                source.matchStatus?.let { status ->
                    SourceMatchStatusPill(
                        status = status,
                        modifier = Modifier.testTag("qa-source-status"),
                    )
                }
            }
            Text(text = source.label, style = MaterialTheme.typography.titleMedium)
            Text(
                text = stringResource(R.string.qa_source_note),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(
                onClick = { onOpenSource(source.url) },
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
                shape = MaterialTheme.shapes.small,
            ) {
                Text(
                    text = stringResource(R.string.action_open_source),
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}
