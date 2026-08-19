package com.mneme.app.ui.qa

import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import com.mneme.app.ui.QaUiState
import com.mneme.app.ui.model.QaUiModel

internal data class QaLocateRequest(
    val turnIndex: Int,
    val question: String,
)

internal data class QaScrollTarget(
    val itemIndex: Int,
    val completed: Boolean = false,
)

internal fun QaUiState.scrollTargetFor(request: QaLocateRequest): QaScrollTarget? =
    when (this) {
        is QaUiState.Loading ->
            if (requestMatches(exchanges.size, question, request)) {
                QaScrollTarget(exchanges.turnStartItemIndex(request.turnIndex) + 1)
            } else {
                null
            }
        is QaUiState.Error ->
            if (requestMatches(exchanges.size, question, request)) {
                QaScrollTarget(exchanges.turnStartItemIndex(request.turnIndex) + 1)
            } else {
                null
            }
        is QaUiState.Content ->
            if (
                exchanges.size > request.turnIndex &&
                exchanges[request.turnIndex].question == request.question
            ) {
                QaScrollTarget(
                    itemIndex = exchanges.turnStartItemIndex(request.turnIndex) + 2,
                    completed = true,
                )
            } else {
                null
            }
        QaUiState.Idle -> null
    }

private fun requestMatches(
    exchangeCount: Int,
    activeQuestion: String,
    request: QaLocateRequest,
): Boolean = exchangeCount == request.turnIndex && activeQuestion == request.question

private fun List<QaUiModel>.turnStartItemIndex(turnIndex: Int): Int =
    1 +
        take(turnIndex).sumOf { exchange ->
            QA_TURN_NON_SOURCE_ITEM_COUNT + maxOf(1, exchange.sources.size)
        }

@Composable
internal fun trackQaScroll(
    paperId: String,
    listState: LazyListState,
    target: QaScrollTarget?,
    onAnswerLocated: () -> Unit,
) {
    LaunchedEffect(paperId) {
        listState.scrollToItem(0)
    }
    LaunchedEffect(paperId, target) {
        target ?: return@LaunchedEffect
        listState.scrollToItem(target.itemIndex)
        if (target.completed) {
            onAnswerLocated()
        }
    }
}

private const val QA_TURN_NON_SOURCE_ITEM_COUNT = 4
