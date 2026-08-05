@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.annotation.StringRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.SourceMatchUiStatus

@Composable
fun MnemeSectionLabel(
    text: String,
    modifier: Modifier = Modifier,
) {
    Text(
        text = text,
        modifier = modifier,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.secondary,
    )
}

@Composable
fun ContentSourceNotice(
    disclosure: ContentDisclosureUiModel,
    modifier: Modifier = Modifier,
    testTag: String? = null,
) {
    val label = disclosure.origin.noticeLabel() ?: return

    val noticeModifier =
        if (testTag == null) {
            modifier
        } else {
            modifier.testTag(testTag)
        }

    Surface(
        modifier = noticeModifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        shape = MaterialTheme.shapes.medium,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.32f)),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = stringResource(label),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = disclosure.message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@StringRes
internal fun ContentOrigin.noticeLabel(): Int? =
    when (this) {
        ContentOrigin.LIVE_BACKEND -> null
        ContentOrigin.CACHED_BACKEND -> R.string.content_source_cached
        ContentOrigin.CONTROLLED_FIXTURE -> R.string.controlled_demo_title
    }

@Composable
fun SourceMatchStatusPill(
    status: SourceMatchUiStatus,
    modifier: Modifier = Modifier,
) {
    val label =
        stringResource(
            when (status) {
                SourceMatchUiStatus.MATCHED -> R.string.source_status_matched
                SourceMatchUiStatus.PARTIAL -> R.string.source_status_partial
                SourceMatchUiStatus.NOT_CHECKED -> R.string.source_status_not_checked
                SourceMatchUiStatus.INSUFFICIENT_EVIDENCE -> R.string.source_status_insufficient
                SourceMatchUiStatus.UNMATCHED -> R.string.source_status_unmatched
            },
        )
    val matched = status == SourceMatchUiStatus.MATCHED
    Surface(
        modifier = modifier,
        color =
            if (matched) {
                MaterialTheme.colorScheme.tertiary
            } else {
                MaterialTheme.colorScheme.surface
            },
        contentColor =
            if (matched) {
                MaterialTheme.colorScheme.onTertiary
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
        shape = MaterialTheme.shapes.extraLarge,
        border = if (matched) null else BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            style = MaterialTheme.typography.labelMedium,
        )
    }
}
