@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.mneme.app.ui.home.HomeScreen
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun MnemeApp(modifier: Modifier = Modifier) {
    HomeScreen(
        state = HomeUiState.Empty,
        onRetry = {},
        onPaperClick = {},
        onDestinationSelected = {},
        modifier = modifier,
    )
}

@Preview(showBackground = true)
@Composable
private fun MnemeAppPreview() {
    MnemeTheme {
        MnemeApp()
    }
}
