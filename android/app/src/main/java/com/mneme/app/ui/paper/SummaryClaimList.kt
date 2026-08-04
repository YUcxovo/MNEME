@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.paper

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.model.ClaimProvenanceUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SummaryClaimUiModel

@Composable
internal fun SummaryClaimList(
    paperId: String,
    claims: List<SummaryClaimUiModel>,
    onOpenPaper: () -> Unit,
) {
    var expandedClaimKey by rememberSaveable(paperId) { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = stringResource(R.string.paper_key_claims),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
        )
        claims.forEachIndexed { index, claim ->
            val claimKey = claim.selectionKey(index)
            SummaryClaimCard(
                claim = claim,
                index = index,
                expanded = expandedClaimKey == claimKey,
                onToggleSource = {
                    expandedClaimKey = if (expandedClaimKey == claimKey) null else claimKey
                },
                onOpenPaper = onOpenPaper,
            )
        }
    }
}

@Composable
private fun SummaryClaimCard(
    claim: SummaryClaimUiModel,
    index: Int,
    expanded: Boolean,
    onToggleSource: () -> Unit,
    onOpenPaper: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().testTag("summary-claim-$index"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.65f)),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = claim.text,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            SourceAffordance(
                claim = claim,
                index = index,
                expanded = expanded,
                onToggleSource = onToggleSource,
                onOpenPaper = onOpenPaper,
            )
        }
    }
}

@Composable
private fun SourceAffordance(
    claim: SummaryClaimUiModel,
    index: Int,
    expanded: Boolean,
    onToggleSource: () -> Unit,
    onOpenPaper: () -> Unit,
) {
    val source = claim.source
    if (claim.matchStatus == SourceMatchUiStatus.MATCHED && source != null) {
        OutlinedButton(
            onClick = onToggleSource,
            modifier = Modifier.testTag("claim-source-action-$index"),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
            shape = MaterialTheme.shapes.small,
        ) {
            val label = if (expanded) R.string.claim_source_hide else R.string.claim_source_view
            Text(text = stringResource(label, index + 1))
        }
        if (expanded) {
            ClaimEvidence(source = source, index = index, onOpenPaper = onOpenPaper)
        }
    } else {
        val message =
            if (claim.matchStatus == SourceMatchUiStatus.NOT_CHECKED) {
                R.string.claim_source_not_checked
            } else {
                R.string.claim_source_unavailable
            }
        Text(
            text = stringResource(message),
            modifier = Modifier.testTag("claim-source-unavailable-$index"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ClaimEvidence(
    source: ClaimProvenanceUiModel,
    index: Int,
    onOpenPaper: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth().testTag("claim-evidence-$index"),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.35f)),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SourceLocation(source)
            Text(
                text = stringResource(R.string.claim_source_excerpt),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = source.excerpt,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            OutlinedButton(
                onClick = onOpenPaper,
                modifier = Modifier.testTag("claim-open-paper-$index"),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
                shape = MaterialTheme.shapes.small,
            ) {
                Text(text = stringResource(R.string.claim_source_open_paper, index + 1))
            }
        }
    }
}

@Composable
private fun SourceLocation(source: ClaimProvenanceUiModel) {
    source.sectionTitle?.let { sectionTitle ->
        Text(
            text = stringResource(R.string.claim_source_section, sectionTitle),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }
    source.pageLabel()?.let { pageLabel ->
        Text(
            text = pageLabel,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun SummaryClaimUiModel.selectionKey(index: Int): String =
    listOf(
        index,
        text,
        matchStatus.name,
        source?.chunkId,
        source?.chunkIndex,
        source?.sectionTitle,
        source?.pageStart,
        source?.pageEnd,
        source?.excerpt,
    ).joinToString(separator = "|")

@Composable
private fun ClaimProvenanceUiModel.pageLabel(): String? {
    val firstPage = pageStart ?: pageEnd ?: return null
    val lastPage = pageEnd ?: firstPage
    return if (lastPage == firstPage) {
        stringResource(R.string.claim_source_page, firstPage)
    } else {
        stringResource(R.string.claim_source_pages, firstPage, lastPage)
    }
}
