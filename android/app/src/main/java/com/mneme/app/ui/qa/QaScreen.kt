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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.component.ControlledDemoNotice
import com.mneme.app.ui.component.MnemeSectionLabel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.theme.MnemeTheme

@Composable
fun QaScreen(
    qa: QaUiModel,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("qa-screen"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            ControlledDemoNotice(disclosure = qa.disclosure)
        }
        item {
            QuestionBubble(question = qa.question)
        }
        item {
            AnswerBubble(answer = qa.answer)
        }
        item {
            MnemeSectionLabel(text = stringResource(R.string.qa_source))
        }
        item {
            QaSourceCard(qa = qa, onOpenSource = onOpenSource)
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
    qa: QaUiModel,
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
            Text(
                text = stringResource(R.string.source_location_format, qa.source.location),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(text = qa.source.label, style = MaterialTheme.typography.titleMedium)
            Text(
                text = stringResource(R.string.qa_source_note),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(
                onClick = { onOpenSource(qa.source.url) },
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
        SeededSkeletalContentRepository.qa(SeededSkeletalContentRepository.PAPER_ID)?.let {
            QaScreen(qa = it, onOpenSource = {})
        }
    }
}
