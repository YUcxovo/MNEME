@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.tooling.preview.Preview
import com.mneme.app.ui.theme.MnemeTheme

@Preview(showBackground = true)
@Composable
private fun MnemeAppPreview() {
    MnemeTheme {
        MnemeApp(onOpenSource = {})
    }
}
