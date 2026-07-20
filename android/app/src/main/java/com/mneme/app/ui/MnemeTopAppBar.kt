@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun MnemeTopAppBar(
    @StringRes titleRes: Int,
    @StringRes kickerRes: Int?,
    showBrandMark: Boolean,
    canNavigateBack: Boolean,
    onNavigateBack: () -> Unit,
) {
    TopAppBar(
        title = {
            MnemeAppBarTitle(
                titleRes = titleRes,
                kickerRes = kickerRes,
                showBrandMark = showBrandMark,
            )
        },
        navigationIcon = {
            if (canNavigateBack) {
                MnemeBackButton(onNavigateBack = onNavigateBack)
            }
        },
        colors =
            TopAppBarDefaults.topAppBarColors(
                containerColor = MaterialTheme.colorScheme.background,
                titleContentColor = MaterialTheme.colorScheme.onBackground,
                navigationIconContentColor = MaterialTheme.colorScheme.onBackground,
            ),
    )
}

@Composable
private fun MnemeAppBarTitle(
    @StringRes titleRes: Int,
    @StringRes kickerRes: Int?,
    showBrandMark: Boolean,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (showBrandMark) {
            MnemeBrandMark()
        }
        Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(
                text = stringResource(titleRes),
                style =
                    if (showBrandMark) {
                        MaterialTheme.typography.titleLarge
                    } else {
                        MaterialTheme.typography.titleMedium
                    },
            )
            kickerRes?.let {
                Text(
                    text = stringResource(it),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun MnemeBrandMark() {
    Surface(
        modifier = Modifier.size(36.dp),
        color = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.primary,
        shape = MaterialTheme.shapes.small,
        border =
            BorderStroke(
                1.dp,
                MaterialTheme.colorScheme.primary.copy(alpha = 0.38f),
            ),
    ) {
        Row(
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.brand_mark),
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

@Composable
private fun MnemeBackButton(onNavigateBack: () -> Unit) {
    Surface(
        modifier = Modifier.padding(start = 8.dp),
        color = MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        IconButton(
            onClick = onNavigateBack,
            modifier = Modifier.testTag("navigate-back"),
        ) {
            Icon(
                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = stringResource(R.string.action_back),
            )
        }
    }
}
