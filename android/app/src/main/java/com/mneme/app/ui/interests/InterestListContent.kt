@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.interests

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.InterestEditUiState
import com.mneme.app.ui.component.MnemeSectionLabel

internal fun LazyListScope.headerItems() {
    item { InterestsHeader() }
    item { MnemeSectionLabel(text = stringResource(R.string.interests_topics_label)) }
}

internal fun LazyListScope.editorItems(
    topics: List<String>,
    onValueChange: (Int, String) -> Unit,
    onRemove: (Int) -> Unit,
) {
    items(topics.size) { index ->
        InterestEditorRow(
            index = index,
            value = topics[index],
            onValueChange = { onValueChange(index, it) },
            onRemove = { onRemove(index) },
        )
    }
}

internal fun LazyListScope.addTopicItem(
    value: String,
    existingTopics: List<String>,
    onValueChange: (String) -> Unit,
    onAdd: () -> Unit,
) {
    item {
        AddInterestRow(
            value = value,
            existingTopics = existingTopics,
            onValueChange = {
                if (it.length <= MAX_TOPIC_LENGTH) onValueChange(it)
            },
            onAdd = onAdd,
        )
    }
}

internal fun LazyListScope.validationItem(message: String?) {
    if (message != null) {
        item {
            FeedbackText(
                text = message,
                isError = true,
                testTag = "interest-validation-error",
            )
        }
    }
}

internal fun LazyListScope.saveItem(
    isDirty: Boolean,
    isValid: Boolean,
    editState: InterestEditUiState,
    onSave: () -> Unit,
) {
    item {
        SaveInterestsButton(
            enabled = isDirty && isValid,
            isSaving = editState == InterestEditUiState.Saving,
            onSave = onSave,
        )
    }
}

internal fun LazyListScope.feedbackItem(
    editState: InterestEditUiState,
    isDirty: Boolean,
) {
    when {
        editState is InterestEditUiState.Error ->
            item {
                FeedbackText(editState.message, true, "interest-save-error")
            }
        editState == InterestEditUiState.Saved && !isDirty ->
            item {
                FeedbackText(
                    stringResource(R.string.interests_saved),
                    false,
                    "interest-save-success",
                )
            }
    }
}

@Composable
private fun SaveInterestsButton(
    enabled: Boolean,
    isSaving: Boolean,
    onSave: () -> Unit,
) {
    Button(
        onClick = onSave,
        enabled = enabled && !isSaving,
        modifier = Modifier.fillMaxWidth().testTag("interest-save"),
    ) {
        if (isSaving) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
        } else {
            Text(stringResource(R.string.interests_save))
        }
    }
}

@Composable
private fun FeedbackText(
    text: String,
    isError: Boolean,
    testTag: String,
) {
    Text(
        text = text,
        color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.testTag(testTag),
    )
}
