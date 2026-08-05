@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.saved

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BookmarkBorder
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
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
import com.mneme.app.ui.SavedPapersUiState
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.component.PaperCard
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun SavedScreen(
    state: SavedPapersUiState,
    onPaperClick: (String) -> Unit,
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(horizontal = 16.dp).testTag("saved-screen"),
        contentPadding = PaddingValues(vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(
                text = stringResource(R.string.screen_title_saved),
                style = MaterialTheme.typography.headlineMedium,
            )
        }
        item { MnemeSectionLabel(text = stringResource(R.string.saved_context_label)) }
        when (state) {
            SavedPapersUiState.Loading -> {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth().testTag("saved-loading"),
                        horizontalArrangement = Arrangement.Center,
                    ) {
                        CircularProgressIndicator()
                    }
                }
            }
            is SavedPapersUiState.Error -> {
                item { SavedErrorState(state.message, onRetry) }
            }
            is SavedPapersUiState.Content -> {
                val papers = state.papers
                if (papers.isEmpty()) {
                    item { SavedEmptyState() }
                } else {
                    item {
                        Text(
                            text =
                                pluralStringResource(
                                    R.plurals.saved_paper_count,
                                    papers.size,
                                    papers.size,
                                ),
                            modifier = Modifier.testTag("saved-paper-count"),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    items(items = papers, key = PaperUiModel::id) { paper ->
                        PaperCard(
                            paper = paper,
                            supportingTextLabel = stringResource(R.string.paper_abstract),
                            onClick = { onPaperClick(paper.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SavedErrorState(
    message: String,
    onRetry: () -> Unit,
) {
    ErrorState(
        message = message,
        onRetry = onRetry,
        modifier = Modifier.testTag("saved-error"),
    )
}

@Composable
private fun SavedEmptyState() {
    Surface(
        modifier = Modifier.fillMaxWidth().testTag("saved-empty-state"),
        color = MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.large,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 24.dp, vertical = 36.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(
                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
                contentColor = MaterialTheme.colorScheme.primary,
                shape = MaterialTheme.shapes.large,
            ) {
                Icon(
                    imageVector = Icons.Outlined.BookmarkBorder,
                    contentDescription = null,
                    modifier = Modifier.padding(14.dp).size(28.dp),
                )
            }
            Text(
                text = stringResource(R.string.saved_empty_title),
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
            )
            Text(
                text = stringResource(R.string.saved_empty_body),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SavedScreenPreview() {
    MnemeTheme {
        SavedScreen(
            state = SavedPapersUiState.Content(emptyList()),
            onPaperClick = {},
        )
    }
}
