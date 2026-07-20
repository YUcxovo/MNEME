@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.qa

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
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
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            ControlledQaNotice(disclosure = qa.disclosure)
        }
        item {
            QaCard(
                title = stringResource(R.string.qa_question),
                body = qa.question,
                testTag = "qa-question",
            )
        }
        item {
            QaCard(
                title = stringResource(R.string.qa_answer),
                body = qa.answer,
                testTag = "qa-answer",
            )
        }
        item {
            QaSourceCard(qa = qa, onOpenSource = onOpenSource)
        }
    }
}

@Composable
private fun ControlledQaNotice(
    disclosure: String,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = stringResource(R.string.controlled_demo_title),
                style = MaterialTheme.typography.titleSmall,
            )
            Text(text = disclosure, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun QaCard(
    title: String,
    body: String,
    testTag: String,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth().testTag(testTag)) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(text = title, style = MaterialTheme.typography.titleMedium)
            Text(text = body, style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun QaSourceCard(
    qa: QaUiModel,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth().testTag("qa-source-card")) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.qa_source),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(text = qa.source.label, style = MaterialTheme.typography.bodyMedium)
            Text(
                text =
                    stringResource(
                        R.string.source_location_format,
                        qa.source.location,
                    ),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(onClick = { onOpenSource(qa.source.url) }) {
                Text(text = stringResource(R.string.action_open_source))
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
