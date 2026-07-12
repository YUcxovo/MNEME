@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.component

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun LoadingState(
    modifier: Modifier = Modifier,
    message: String = "Loading your research feed...",
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text(text = message, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun ErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = "Something went wrong", style = MaterialTheme.typography.titleMedium)
        Text(text = message, style = MaterialTheme.typography.bodyMedium)
        Button(onClick = onRetry) { Text("Try again") }
    }
}

@Preview(showBackground = true)
@Composable
private fun ContentStatesPreview() {
    MnemeTheme {
        ErrorState(message = "The feed could not be refreshed.", onRetry = {})
    }
}
