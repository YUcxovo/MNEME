@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.paper

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun PaperDetailScreen(
    paper: PaperDetailUiModel,
    onAskQuestion: () -> Unit,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("paper-detail-screen"),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        paperDetailItems(
            paper = paper,
            onAskQuestion = onAskQuestion,
            onOpenSource = onOpenSource,
        )
    }
}

private fun LazyListScope.paperDetailItems(
    paper: PaperDetailUiModel,
    onAskQuestion: () -> Unit,
    onOpenSource: (String) -> Unit,
) {
    item {
        ControlledContentLabel(disclosure = paper.disclosure)
    }
    item {
        PaperHeader(paper = paper)
    }
    item {
        PaperSection(
            title = stringResource(R.string.paper_abstract),
            body = paper.abstractText,
        )
    }
    item {
        PaperSection(
            title = stringResource(R.string.paper_basic_summary),
            body = paper.paper.summary,
            testTag = "basic-summary",
        )
    }
    item {
        Text(
            text = stringResource(R.string.paper_key_claims),
            style = MaterialTheme.typography.titleMedium,
        )
    }
    items(paper.keyClaims, key = { it }) { claim ->
        Text(text = "- $claim", style = MaterialTheme.typography.bodyMedium)
    }
    item {
        PaperSection(
            title = stringResource(R.string.paper_methodology),
            body = paper.methodology,
        )
    }
    item {
        PaperSection(
            title = stringResource(R.string.paper_limitation),
            body = paper.limitation,
        )
    }
    item {
        SourceCard(
            label = paper.source.label,
            location = paper.source.location,
            onOpenSource = { onOpenSource(paper.source.url) },
        )
    }
    item {
        Button(
            onClick = onAskQuestion,
            modifier = Modifier.fillMaxWidth().testTag("ask-question-action"),
        ) {
            Text(text = stringResource(R.string.action_ask_seeded_question))
        }
    }
}

@Composable
private fun PaperHeader(paper: PaperDetailUiModel) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(text = paper.paper.title, style = MaterialTheme.typography.headlineSmall)
        Text(
            text = paper.paper.authors,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = paper.paper.category,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}

@Composable
private fun ControlledContentLabel(
    disclosure: String,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = stringResource(R.string.controlled_demo_title),
                style = MaterialTheme.typography.titleSmall,
            )
            Text(text = disclosure, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun PaperSection(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    testTag: String? = null,
) {
    val sectionModifier = if (testTag == null) modifier else modifier.testTag(testTag)
    Column(
        modifier = sectionModifier,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(text = title, style = MaterialTheme.typography.titleMedium)
        Text(text = body, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun SourceCard(
    label: String,
    location: String,
    onOpenSource: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth().testTag("paper-source-card")) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.paper_source),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(text = label, style = MaterialTheme.typography.bodyMedium)
            Text(
                text = stringResource(R.string.source_location_format, location),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(onClick = onOpenSource) {
                Text(text = stringResource(R.string.action_open_source))
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun PaperDetailScreenPreview() {
    MnemeTheme {
        SeededSkeletalContentRepository.paper(SeededSkeletalContentRepository.PAPER_ID)?.let {
            PaperDetailScreen(
                paper = it,
                onAskQuestion = {},
                onOpenSource = {},
            )
        }
    }
}
