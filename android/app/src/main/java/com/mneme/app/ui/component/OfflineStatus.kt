@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

sealed interface OfflineStatus {
    data object OfflineWithoutCache : OfflineStatus

    data class ShowingCachedContent(
        val lastUpdatedLabel: String,
    ) : OfflineStatus
}

@Composable
fun OfflineStatusBanner(
    status: OfflineStatus,
    modifier: Modifier = Modifier,
) {
    val message =
        when (status) {
            OfflineStatus.OfflineWithoutCache -> "You're offline. Connect to load your research feed."
            is OfflineStatus.ShowingCachedContent -> "Offline - Last updated ${status.lastUpdatedLabel}"
        }
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        contentColor = MaterialTheme.colorScheme.onSurfaceVariant,
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
