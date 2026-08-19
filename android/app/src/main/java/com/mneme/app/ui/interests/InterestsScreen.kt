@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.interests

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.InterestEditUiState
import com.mneme.app.ui.component.ContentSourceNotice
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun InterestsScreen(
    interests: List<String>,
    disclosure: ContentDisclosureUiModel,
    editState: InterestEditUiState,
    onSave: (List<String>) -> Unit,
    modifier: Modifier = Modifier,
) {
    var draftTopics by remember(interests) { mutableStateOf(interests) }
    var newTopic by rememberSaveable { mutableStateOf("") }
    val validation = validateDraft(draftTopics)
    val validationMessage = validation.messageResource?.let { stringResource(it) }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("interests-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        headerItems()
        editorItems(
            topics = draftTopics,
            onValueChange = { index, value ->
                draftTopics = draftTopics.replacing(index, value)
            },
            onRemove = { index -> draftTopics = draftTopics.removing(index) },
        )
        addTopicItem(
            value = newTopic,
            existingTopics = validation.trimmedTopics,
            onValueChange = { newTopic = it },
            onAdd = {
                draftTopics = draftTopics + newTopic.trim()
                newTopic = ""
            },
        )
        validationItem(validationMessage)
        saveItem(
            isDirty = validation.normalizedTopics != interests,
            isValid = validationMessage == null,
            editState = editState,
            onSave = { onSave(validation.normalizedTopics) },
        )
        feedbackItem(editState, validation.normalizedTopics != interests)
        item { ContentSourceNotice(disclosure = disclosure) }
    }
}

@Composable
internal fun InterestsHeader() {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(
            text = stringResource(R.string.screen_title_interests),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = stringResource(R.string.interests_description),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
internal fun InterestEditorRow(
    index: Int,
    value: String,
    onValueChange: (String) -> Unit,
    onRemove: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = { Text(stringResource(R.string.interests_topic_number, index + 1)) },
            singleLine = true,
            modifier = Modifier.weight(1f).testTag("interest-topic-$index"),
        )
        TextButton(
            onClick = onRemove,
            modifier = Modifier.testTag("interest-remove-$index"),
        ) {
            Text(stringResource(R.string.interests_remove))
        }
    }
}

@Composable
internal fun AddInterestRow(
    value: String,
    existingTopics: List<String>,
    onValueChange: (String) -> Unit,
    onAdd: () -> Unit,
) {
    val normalized = value.trim()
    val canAdd =
        normalized.isNotEmpty() &&
            existingTopics.none { it.equals(normalized, ignoreCase = true) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = { Text(stringResource(R.string.interests_new_topic)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("interest-new-topic"),
        )
        Button(
            onClick = onAdd,
            enabled = canAdd,
            modifier = Modifier.testTag("interest-add"),
        ) {
            Text(stringResource(R.string.interests_add))
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun InterestsScreenPreview() {
    MnemeTheme {
        val briefing = SeededSkeletalContentRepository.briefing()
        InterestsScreen(
            interests = briefing.interests,
            disclosure = briefing.disclosure,
            editState = InterestEditUiState.Idle,
            onSave = {},
        )
    }
}

internal const val MAX_TOPIC_LENGTH = 100
