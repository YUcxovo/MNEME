@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.qa

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.runtime.remember
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
import com.mneme.app.ui.completedExchanges
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun QaScreen(
    paperId: String,
    state: QaUiState,
    onSubmit: (String) -> Unit,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var question by rememberSaveable(paperId) { mutableStateOf("") }
    var locateRequest by remember(paperId) { mutableStateOf<QaLocateRequest?>(null) }
    val isLoading = state is QaUiState.Loading
    val listState = rememberLazyListState()
    val completedExchanges = state.completedExchanges()
    val focusManager = LocalFocusManager.current
    val submitQuestion = {
        if (question.isNotBlank() && question.length <= QUESTION_MAX_LENGTH && !isLoading) {
            val submitted = question
            question = ""
            locateRequest = QaLocateRequest(completedExchanges.size, submitted)
            focusManager.clearFocus()
            onSubmit(submitted)
        }
    }
    trackQaScroll(
        paperId = paperId,
        listState = listState,
        target = locateRequest?.let(state::scrollTargetFor),
        onAnswerLocated = { locateRequest = null },
    )
    QaConversationList(
        modifier = modifier.fillMaxSize().testTag("qa-screen"),
        listState = listState,
        content =
            QaConversationContent(
                state = state,
                completedExchanges = completedExchanges,
                question = question,
                isLoading = isLoading,
            ),
        actions =
            QaConversationActions(
                onQuestionChange = { updated -> question = updated },
                onSubmit = submitQuestion,
                onRetry = onSubmit,
                onOpenSource = onOpenSource,
            ),
    )
}

private data class QaConversationContent(
    val state: QaUiState,
    val completedExchanges: List<QaUiModel>,
    val question: String,
    val isLoading: Boolean,
)

private data class QaConversationActions(
    val onQuestionChange: (String) -> Unit,
    val onSubmit: () -> Unit,
    val onRetry: (String) -> Unit,
    val onOpenSource: (String) -> Unit,
)

@Composable
private fun QaConversationList(
    content: QaConversationContent,
    actions: QaConversationActions,
    listState: LazyListState,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier,
        state = listState,
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            QuestionComposer(
                question = content.question,
                isLoading = content.isLoading,
                onQuestionChange = { updated ->
                    if (updated.length <= QUESTION_MAX_LENGTH) {
                        actions.onQuestionChange(updated)
                    }
                },
                onSubmit = actions.onSubmit,
            )
        }
        content.completedExchanges.forEachIndexed { index, exchange ->
            item { QuestionBubble(question = exchange.question) }
            qaResponseItems(
                qa = exchange,
                turnIndex = index,
                onOpenSource = actions.onOpenSource,
            )
        }
        qaStateItems(state = content.state, onSubmit = actions.onRetry)
    }
}

private fun LazyListScope.qaStateItems(
    state: QaUiState,
    onSubmit: (String) -> Unit,
) {
    when (state) {
        QaUiState.Idle -> {
            qaEmptyPrompt()
        }
        is QaUiState.Loading -> {
            item { QuestionBubble(question = state.question) }
            item { QaLoadingState() }
        }
        is QaUiState.Error -> {
            item { QuestionBubble(question = state.question) }
            item {
                QaErrorState(
                    message = state.message,
                    onRetry = { onSubmit(state.question) },
                )
            }
        }
        is QaUiState.Content -> {
            if (state.exchanges.isEmpty()) {
                qaEmptyPrompt()
            }
        }
    }
}

private fun LazyListScope.qaEmptyPrompt() {
    item {
        Text(
            text = stringResource(R.string.qa_empty_prompt),
            modifier = Modifier.testTag("qa-empty-prompt"),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
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

@Preview(showBackground = true)
@Composable
private fun QaScreenPreview() {
    MnemeTheme {
        val question = "What evidence supports the paper's main conclusion?"
        SeededSkeletalContentRepository.qa(SeededSkeletalContentRepository.PAPER_ID, question)?.let {
            QaScreen(
                paperId = SeededSkeletalContentRepository.PAPER_ID,
                state =
                    QaUiState.Content(
                        paperId = SeededSkeletalContentRepository.PAPER_ID,
                        exchanges = listOf(it),
                    ),
                onSubmit = {},
                onOpenSource = {},
            )
        }
    }
}
