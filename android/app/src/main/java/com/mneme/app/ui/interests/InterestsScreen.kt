@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.interests

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.mneme.app.ui.component.FilterChip
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun InterestsScreen(
    interests: List<String>,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("interests-screen"),
        contentPadding = PaddingValues(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = stringResource(R.string.interests_description),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        items(interests, key = { it }) { interest ->
            FilterChip(
                label = interest,
                selected = true,
                onSelectedChange = {},
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun InterestsScreenPreview() {
    MnemeTheme {
        InterestsScreen(
            interests = SeededSkeletalContentRepository.briefing().interests,
        )
    }
}
