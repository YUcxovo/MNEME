@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.component.DigestCard
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.FilterChip
import com.mneme.app.ui.component.LoadingState
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
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            ControlledDemoNotice(disclosure = briefing.disclosure)
        }
        item {
            DigestCard(digest = briefing.digest)
        }
        item {
            Text(
                text = stringResource(R.string.briefing_seeded_interests),
                style = MaterialTheme.typography.titleMedium,
            )
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(briefing.interests, key = { it }) { interest ->
                    FilterChip(
                        label = interest,
                        selected = true,
                        onSelectedChange = {},
                    )
                }
            }
        }
        item {
            Text(
                text = stringResource(R.string.briefing_recommended_paper),
                style = MaterialTheme.typography.titleMedium,
            )
        }
        items(items = briefing.papers, key = PaperUiModel::id) { paper ->
            PaperCard(
                paper = paper,
                onClick = { onPaperClick(paper.id) },
            )
        }
    }
}

@Composable
private fun ControlledDemoNotice(
    disclosure: String,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth().testTag("controlled-demo-notice"),
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
