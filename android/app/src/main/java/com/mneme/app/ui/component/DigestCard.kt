@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    val cardModifier =
        if (onClick == null) {
            modifier.fillMaxWidth()
        } else {
            modifier.fillMaxWidth().clickable(onClick = onClick)
        }
    Card(
        modifier = cardModifier,
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface,
            ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = digest.dateLabel,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(text = digest.title, style = MaterialTheme.typography.titleLarge)
            Text(
                text = digest.summary,
                maxLines = 4,
                overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
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
            modifier = Modifier.padding(16.dp),
        )
    }
}
