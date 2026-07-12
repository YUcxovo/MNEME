@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.mneme.app.ui.theme.MnemeTheme
import androidx.compose.material3.FilterChip as MaterialFilterChip

@Composable
fun FilterChip(
    label: String,
    selected: Boolean,
    onSelectedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    MaterialFilterChip(
        selected = selected,
        onClick = { onSelectedChange(!selected) },
        label = { Text(label) },
        modifier = modifier,
    )
}

@Preview(showBackground = true)
@Composable
private fun FilterChipPreview() {
    MnemeTheme {
        FilterChip(label = "Computer vision", selected = true, onSelectedChange = {})
    }
}
