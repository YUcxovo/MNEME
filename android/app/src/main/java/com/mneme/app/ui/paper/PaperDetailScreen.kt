@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.paper

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
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
import com.mneme.app.ui.component.ContentSourceNotice
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.component.SourceMatchStatusPill
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun PaperDetailScreen(
    paper: PaperDetailUiModel,
    actions: PaperDetailActions,
    isSaved: Boolean,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("paper-detail-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            PaperHeader(paper = paper)
        }
        item {
            ContentSourceNotice(disclosure = paper.disclosure)
        }
        item {
            PaperSummaryCard(paper = paper)
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                MnemeSectionLabel(text = stringResource(R.string.paper_source_trace))
                SourceMatchStatusPill(status = paper.sourceMatchStatus)
            }
        }
        item {
            SourceCard(
                label = paper.source.label,
                location = paper.source.location,
                onOpenSource = { actions.openSource(paper.source.url) },
            )
        }
        item {
            PaperActions(
                actions = actions,
                isSaved = isSaved,
            )
        }
    }
}

@Composable
private fun PaperActions(
    actions: PaperDetailActions,
    isSaved: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        PaperEngagementActions(
            onSavePaper = actions.savePaper,
            onSharePaper = actions.sharePaper,
            isSaved = isSaved,
        )
        OutlinedButton(
            onClick = actions.exploreGraph,
            modifier = Modifier.fillMaxWidth().testTag("explore-graph-action"),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
            shape = MaterialTheme.shapes.small,
        ) {
            Icon(
                imageVector = Icons.Default.AccountTree,
                contentDescription = null,
            )
            Text(
                text = stringResource(R.string.action_explore_graph),
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        Button(
            onClick = actions.askQuestion,
            modifier = Modifier.fillMaxWidth().testTag("ask-question-action"),
            colors =
                ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            shape = MaterialTheme.shapes.small,
        ) {
            Icon(
                imageVector = Icons.AutoMirrored.Filled.MenuBook,
                contentDescription = null,
            )
            Text(
                text = stringResource(R.string.action_ask_question),
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun PaperEngagementActions(
    onSavePaper: () -> Unit,
    onSharePaper: () -> Unit,
    isSaved: Boolean,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Button(
            onClick = onSavePaper,
            enabled = !isSaved,
            modifier = Modifier.weight(1f).testTag("save-paper-action"),
            shape = MaterialTheme.shapes.small,
        ) {
            Icon(imageVector = Icons.Default.Bookmark, contentDescription = null)
            Text(
                text =
                    stringResource(
                        if (isSaved) R.string.action_saved else R.string.action_save_paper,
                    ),
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        OutlinedButton(
            onClick = onSharePaper,
            modifier = Modifier.weight(1f).testTag("share-paper-action"),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
            shape = MaterialTheme.shapes.small,
        ) {
            Icon(imageVector = Icons.Default.Share, contentDescription = null)
            Text(
                text = stringResource(R.string.action_share_paper),
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun PaperHeader(paper: PaperDetailUiModel) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(text = paper.paper.title, style = MaterialTheme.typography.headlineMedium)
        Text(
            text = paper.paper.authors,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Surface(
            color = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.secondary,
            shape = MaterialTheme.shapes.extraLarge,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        ) {
            Text(
                text = paper.paper.category,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun PaperSummaryCard(
    paper: PaperDetailUiModel,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
            ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PaperSection(
                title = stringResource(R.string.paper_abstract),
                body = paper.abstractText,
            )
            SummaryDivider()
            PaperSection(
                title = stringResource(R.string.paper_basic_summary),
                body = paper.paper.summary,
                testTag = "basic-summary",
            )
            if (paper.keyClaims.isNotEmpty()) {
                SummaryDivider()
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = stringResource(R.string.paper_key_claims),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    paper.keyClaims.forEach { claim ->
                        Text(
                            text = "\u2022  $claim",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                    }
                }
            }
            paper.methodology?.takeIf(String::isNotBlank)?.let { methodology ->
                SummaryDivider()
                PaperSection(
                    title = stringResource(R.string.paper_methodology),
                    body = methodology,
                )
            }
            paper.limitation?.takeIf(String::isNotBlank)?.let { limitation ->
                SummaryDivider()
                PaperSection(
                    title = stringResource(R.string.paper_limitation),
                    body = limitation,
                    muted = true,
                )
            }
        }
    }
}

@Composable
private fun SummaryDivider() {
    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.7f))
}

@Composable
private fun PaperSection(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    testTag: String? = null,
    muted: Boolean = false,
) {
    val sectionModifier = if (testTag == null) modifier else modifier.testTag(testTag)
    Column(
        modifier = sectionModifier,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = body,
            style = MaterialTheme.typography.bodyMedium,
            color =
                if (muted) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    MaterialTheme.colorScheme.onSurface
                },
        )
    }
}

@Composable
private fun SourceCard(
    label: String,
    location: String,
    onOpenSource: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("paper-source-card"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.42f)),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.source_location_format, location),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(text = label, style = MaterialTheme.typography.titleMedium)
            Text(
                text = stringResource(R.string.paper_source_inspectable),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(
                onClick = onOpenSource,
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

@Preview(showBackground = true)
@Composable
private fun PaperDetailScreenPreview() {
    MnemeTheme {
        SeededSkeletalContentRepository.paper(SeededSkeletalContentRepository.PAPER_ID)?.let {
            PaperDetailScreen(
                paper = it,
                actions =
                    PaperDetailActions(
                        askQuestion = {},
                        exploreGraph = {},
                        savePaper = {},
                        sharePaper = {},
                        openSource = {},
                    ),
                isSaved = false,
            )
        }
    }
}
