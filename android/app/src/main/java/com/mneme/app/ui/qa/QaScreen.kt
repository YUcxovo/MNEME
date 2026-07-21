@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.qa

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.network.QUESTION_MAX_LENGTH
import com.mneme.app.ui.QaUiState
import com.mneme.app.ui.component.ContentSourceNotice
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.component.SourceMatchStatusPill
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceUiModel
import com.mneme.app.ui.submittedQuestion
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun QaScreen(
    paperId: String,
    state: QaUiState,
    onSubmit: (String) -> Unit,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val initialQuestion = state.submittedQuestion().orEmpty()
    var question by rememberSaveable(paperId) { mutableStateOf(initialQuestion) }
    val isLoading = state is QaUiState.Loading
    val focusManager = LocalFocusManager.current
    val submitQuestion = {
        if (question.isNotBlank() && question.length <= QUESTION_MAX_LENGTH && !isLoading) {
            focusManager.clearFocus()
            onSubmit(question)
        }
    }

    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("qa-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            QuestionComposer(
                question = question,
                isLoading = isLoading,
                onQuestionChange = { updated ->
                    if (updated.length <= QUESTION_MAX_LENGTH) {
                        question = updated
                    }
                },
                onSubmit = submitQuestion,
            )
        }

        state.submittedQuestion()?.let { submittedQuestion ->
            item {
                QuestionBubble(question = submittedQuestion)
            }
        }

        qaStateItems(state = state, onSubmit = onSubmit, onOpenSource = onOpenSource)
    }
}

private fun LazyListScope.qaStateItems(
    state: QaUiState,
    onSubmit: (String) -> Unit,
    onOpenSource: (String) -> Unit,
) {
    when (state) {
        QaUiState.Idle -> {
            item {
                Text(
                    text = stringResource(R.string.qa_empty_prompt),
                    modifier = Modifier.testTag("qa-empty-prompt"),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        is QaUiState.Loading -> {
            item { QaLoadingState() }
        }
        is QaUiState.Error -> {
            item {
                QaErrorState(
                    message = state.message,
                    onRetry = { onSubmit(state.question) },
                )
            }
        }
        is QaUiState.Content -> {
            qaResponseItems(qa = state.qa, onOpenSource = onOpenSource)
        }
    }
}

@Composable
private fun QuestionComposer(
    question: String,
    isLoading: Boolean,
    onQuestionChange: (String) -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val canSubmit = question.isNotBlank() && question.length <= QUESTION_MAX_LENGTH && !isLoading
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            MnemeSectionLabel(text = stringResource(R.string.qa_ask_label))
            Text(
                text = stringResource(R.string.qa_ask_description),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = question,
                onValueChange = onQuestionChange,
                modifier = Modifier.fillMaxWidth().testTag("qa-question-input"),
                enabled = !isLoading,
                label = { Text(stringResource(R.string.qa_input_label)) },
                placeholder = { Text(stringResource(R.string.qa_input_placeholder)) },
                supportingText = {
                    Text(
                        text =
                            stringResource(
                                R.string.qa_character_count,
                                question.length,
                                QUESTION_MAX_LENGTH,
                            ),
                    )
                },
                minLines = 3,
                maxLines = 5,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions =
                    KeyboardActions(
                        onSend = {
                            if (canSubmit) {
                                onSubmit()
                            }
                        },
                    ),
            )
            Button(
                onClick = onSubmit,
                enabled = canSubmit,
                modifier = Modifier.fillMaxWidth().testTag("qa-submit-question"),
                shape = MaterialTheme.shapes.small,
            ) {
                Text(stringResource(R.string.qa_submit_question))
            }
        }
    }
}

private fun LazyListScope.qaResponseItems(
    qa: QaUiModel,
    onOpenSource: (String) -> Unit,
) {
    item {
        ContentSourceNotice(disclosure = qa.disclosure)
    }
    item {
        AnswerBubble(answer = qa.answer)
    }
    item {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            MnemeSectionLabel(text = stringResource(R.string.qa_source))
            SourceMatchStatusPill(status = qa.sourceMatchStatus)
        }
    }
    if (qa.sources.isEmpty()) {
        item {
            Text(
                text = stringResource(R.string.qa_no_citations),
                modifier = Modifier.testTag("qa-no-citations"),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    } else {
        items(
            items = qa.sources,
            key = { source -> "${source.url}-${source.location}" },
        ) { source ->
            QaSourceCard(source = source, onOpenSource = onOpenSource)
        }
    }
}

@Composable
private fun QaLoadingState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth().padding(vertical = 20.dp).testTag("qa-loading"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CircularProgressIndicator()
        Text(
            text = stringResource(R.string.qa_loading),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun QaErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("qa-error"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = stringResource(R.string.qa_error_title),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            OutlinedButton(onClick = onRetry) {
                Text(stringResource(R.string.qa_retry_question))
            }
        }
    }
}

@Composable
private fun QuestionBubble(
    question: String,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.fillMaxWidth()) {
        Surface(
            modifier =
                Modifier
                    .align(Alignment.CenterEnd)
                    .widthIn(max = 320.dp)
                    .testTag("qa-question"),
            color = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
            shape = RoundedCornerShape(18.dp, 18.dp, 6.dp, 18.dp),
        ) {
            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Text(
                    text = stringResource(R.string.qa_question),
                    style = MaterialTheme.typography.labelSmall,
                )
                Text(text = question, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun AnswerBubble(
    answer: String,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("qa-answer"),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
            ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = RoundedCornerShape(6.dp, 18.dp, 18.dp, 18.dp),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.qa_answer),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = answer,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun QaSourceCard(
    source: SourceUiModel,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag("qa-source-card"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.42f)),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.source_location_format, source.location),
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
                source.matchStatus?.let { status ->
                    SourceMatchStatusPill(
                        status = status,
                        modifier = Modifier.testTag("qa-source-status"),
                    )
                }
            }
            Text(text = source.label, style = MaterialTheme.typography.titleMedium)
            Text(
                text = stringResource(R.string.qa_source_note),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(
                onClick = { onOpenSource(source.url) },
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
                shape = MaterialTheme.shapes.small,
            ) {
                Text(
                    text = stringResource(R.string.action_open_source),
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun QaScreenPreview() {
    MnemeTheme {
        val question = "What evidence supports the paper's main conclusion?"
        SeededSkeletalContentRepository.qa(SeededSkeletalContentRepository.PAPER_ID, question)?.let {
            QaScreen(
                paperId = SeededSkeletalContentRepository.PAPER_ID,
                state = QaUiState.Content(it),
                onSubmit = {},
                onOpenSource = {},
            )
        }
    }
}
