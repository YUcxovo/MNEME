@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.mneme.app.R

@Composable
fun SeedOnboardingScreen(
    initialReference: String,
    errorMessage: String?,
    onSubmit: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var reference by remember(initialReference) { mutableStateOf(initialReference) }
    val canSubmit = reference.isNotBlank()
    val submit = { if (canSubmit) onSubmit(reference.trim()) }

    Column(
        modifier =
            modifier
                .fillMaxSize()
                .padding(horizontal = 24.dp, vertical = 36.dp)
                .testTag("seed-onboarding-screen"),
        verticalArrangement = Arrangement.Center,
    ) {
        SeedOnboardingIntro()
        Spacer(modifier = Modifier.height(24.dp))
        SeedReferenceField(
            reference = reference,
            errorMessage = errorMessage,
            onReferenceChange = { reference = it },
            onSubmit = submit,
        )
        Spacer(modifier = Modifier.height(18.dp))
        Button(
            onClick = submit,
            enabled = canSubmit,
            modifier = Modifier.fillMaxWidth().testTag("seed-paper-submit"),
        ) {
            Text(
                text = stringResource(R.string.onboarding_submit),
                textAlign = TextAlign.Center,
            )
        }
        Spacer(modifier = Modifier.height(12.dp))
        Text(
            text = stringResource(R.string.onboarding_wait_note),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SeedOnboardingIntro() {
    Text(
        text = stringResource(R.string.onboarding_brand),
        style = MaterialTheme.typography.displaySmall,
        color = MaterialTheme.colorScheme.primary,
    )
    Spacer(modifier = Modifier.height(12.dp))
    Text(
        text = stringResource(R.string.onboarding_title),
        style = MaterialTheme.typography.headlineMedium,
    )
    Spacer(modifier = Modifier.height(8.dp))
    Text(
        text = stringResource(R.string.onboarding_description),
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun SeedReferenceField(
    reference: String,
    errorMessage: String?,
    onReferenceChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    OutlinedTextField(
        value = reference,
        onValueChange = onReferenceChange,
        modifier = Modifier.fillMaxWidth().testTag("seed-paper-input"),
        label = { Text(stringResource(R.string.onboarding_input_label)) },
        placeholder = { Text(stringResource(R.string.onboarding_input_placeholder)) },
        singleLine = true,
        isError = errorMessage != null,
        supportingText =
            errorMessage?.let { message ->
                {
                    Text(
                        text = message,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            },
        keyboardOptions =
            KeyboardOptions(
                keyboardType = KeyboardType.Uri,
                imeAction = ImeAction.Done,
            ),
        keyboardActions = KeyboardActions(onDone = { onSubmit() }),
    )
}
