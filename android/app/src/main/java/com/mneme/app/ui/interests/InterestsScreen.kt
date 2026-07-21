@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.interests

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
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
import com.mneme.app.ui.component.FilterChip
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun InterestsScreen(
    interests: List<String>,
    disclosure: ContentDisclosureUiModel,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("interests-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { InterestsHeader() }
        item {
            MnemeSectionLabel(text = stringResource(R.string.interests_topics_label))
        }
        item { InterestChips(interests = interests) }
        item { ContentSourceNotice(disclosure = disclosure) }
    }
}

@Composable
private fun InterestsHeader() {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(
            text = stringResource(R.string.screen_title_interests),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = stringResource(R.string.interests_description),
            style = MaterialTheme.typography.bodyMedium,
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

@Preview(showBackground = true)
@Composable
private fun InterestsScreenPreview() {
    MnemeTheme {
        val briefing = SeededSkeletalContentRepository.briefing()
        InterestsScreen(
            interests = briefing.interests,
            disclosure = briefing.disclosure,
        )
    }
}
