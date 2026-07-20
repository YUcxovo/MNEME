@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.component.ControlledDemoNotice
import com.mneme.app.ui.component.DigestCard
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.FilterChip
import com.mneme.app.ui.component.LoadingState
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.component.PaperCard
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun HomeScreen(
    state: HomeUiState,
    onRetry: () -> Unit,
    onPaperClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize().testTag("briefing-screen"),
    ) {
        when (state) {
            HomeUiState.Loading -> LoadingState()
            HomeUiState.Empty -> EmptyHomeState()
            is HomeUiState.Error -> ErrorState(message = state.message, onRetry = onRetry)
            is HomeUiState.Content -> {
                BriefingFeed(
                    briefing = state.briefing,
                    onPaperClick = onPaperClick,
                )
            }
        }
    }
}

@Composable
private fun EmptyHomeState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(32.dp).testTag("home-empty-state"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = stringResource(R.string.home_empty_title),
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
        )
        Text(
            text = stringResource(R.string.home_empty_body),
            modifier = Modifier.padding(top = 12.dp),
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun BriefingFeed(
    briefing: BriefingUiModel,
    onPaperClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        briefingItems(briefing = briefing, onPaperClick = onPaperClick)
    }
}

private fun LazyListScope.briefingItems(
    briefing: BriefingUiModel,
    onPaperClick: (String) -> Unit,
) {
    item { BriefingHeader(paperCount = briefing.papers.size) }
    item {
        ControlledDemoNotice(
            disclosure = briefing.disclosure,
            testTag = "controlled-demo-notice",
        )
    }
    item { DigestCard(digest = briefing.digest) }
    item {
        MnemeSectionLabel(text = stringResource(R.string.briefing_seeded_interests))
    }
    item { InterestChips(interests = briefing.interests) }
    item { RecommendedHeader(paperCount = briefing.papers.size) }
    items(items = briefing.papers, key = PaperUiModel::id) { paper ->
        PaperCard(
            paper = paper,
            onClick = { onPaperClick(paper.id) },
        )
    }
}

@Composable
private fun BriefingHeader(paperCount: Int) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.briefing_today),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text =
                pluralStringResource(
                    R.plurals.briefing_match_summary,
                    paperCount,
                    paperCount,
                ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun InterestChips(interests: List<String>) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        interests.forEach { interest ->
            FilterChip(
                label = interest,
                selected = true,
            )
        }
    }
}

@Composable
private fun RecommendedHeader(paperCount: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        MnemeSectionLabel(text = stringResource(R.string.briefing_recommended_paper))
        Text(
            text = stringResource(R.string.briefing_paper_count, paperCount),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun HomeScreenPreview() {
    MnemeTheme {
        HomeScreen(
            state = HomeUiState.Content(SeededSkeletalContentRepository.briefing()),
            onRetry = {},
            onPaperClick = {},
        )
    }
}
