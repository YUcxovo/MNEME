@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.ui.model.DigestUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun DigestCard(
    digest: DigestUiModel,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier =
            modifier
                .fillMaxWidth()
                .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(text = digest.dateLabel, style = MaterialTheme.typography.labelMedium)
            Text(text = digest.title, style = MaterialTheme.typography.titleMedium)
            Text(
                text = digest.summary,
                maxLines = 4,
                overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun DigestCardPreview() {
    MnemeTheme {
        DigestCard(
            digest =
                DigestUiModel(
                    id = "digest-1",
                    title = "Your daily research digest",
                    summary = "Highlights from the papers selected for your interests.",
                    dateLabel = "Today",
                ),
            onClick = {},
            modifier = Modifier.padding(16.dp),
        )
    }
}
