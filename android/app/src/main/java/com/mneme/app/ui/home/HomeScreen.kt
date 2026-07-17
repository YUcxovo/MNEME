@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.LoadingState
import com.mneme.app.ui.component.PaperCard
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.theme.MnemeTheme

enum class HomeDestination(
    val label: String,
    val symbol: String,
) {
    HOME("Home", "H"),
    DIGEST("Digest", "D"),
    SAVED("Saved", "S"),
    SETTINGS("Settings", "P"),
}

sealed interface HomeUiState {
    data object Loading : HomeUiState

    data object Empty : HomeUiState

    data class Error(
        val message: String,
    ) : HomeUiState

    data class Content(
        val papers: List<PaperUiModel>,
    ) : HomeUiState
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    state: HomeUiState,
    onRetry: () -> Unit,
    onPaperClick: (String) -> Unit,
    onDestinationSelected: (HomeDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier.fillMaxSize().testTag("home-screen"),
        topBar = { TopAppBar(title = { Text("Mneme") }) },
        bottomBar = {
            NavigationBar {
                HomeDestination.entries.forEach { destination ->
                    NavigationBarItem(
                        selected = destination == HomeDestination.HOME,
                        onClick = { onDestinationSelected(destination) },
                        icon = { Text(destination.symbol) },
                        label = { Text(destination.label) },
                    )
                }
            }
        },
    ) { innerPadding ->
        when (state) {
            HomeUiState.Loading -> LoadingState(modifier = Modifier.padding(innerPadding))
            HomeUiState.Empty -> EmptyHomeState(modifier = Modifier.padding(innerPadding))
            is HomeUiState.Error -> {
                ErrorState(
                    message = state.message,
                    onRetry = onRetry,
                    modifier = Modifier.padding(innerPadding),
                )
            }
            is HomeUiState.Content -> {
                PaperFeed(
                    papers = state.papers,
                    onPaperClick = onPaperClick,
                    contentPadding = innerPadding,
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
            text = "Your research feed is ready for its first paper.",
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
        )
        Text(
            text = "Choose topics in Settings to personalize future digests.",
            modifier = Modifier.padding(top = 12.dp),
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun PaperFeed(
    papers: List<PaperUiModel>,
    onPaperClick: (String) -> Unit,
    contentPadding: PaddingValues,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        items(items = papers, key = PaperUiModel::id) { paper ->
            PaperCard(
                paper = paper,
                onClick = { onPaperClick(paper.id) },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun HomeScreenPreview() {
    MnemeTheme {
        HomeScreen(
            state = HomeUiState.Empty,
            onRetry = {},
            onPaperClick = {},
            onDestinationSelected = {},
        )
    }
}
