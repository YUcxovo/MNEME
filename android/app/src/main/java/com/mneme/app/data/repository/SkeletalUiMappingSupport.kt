package com.mneme.app.data.repository

import com.mneme.app.data.local.CachedPaper
import com.mneme.app.data.network.PaperDto
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

internal fun PaperDto.toPaperUi(summary: String): PaperUiModel =
    PaperUiModel(
        id = id,
        title = title,
        authors = authors.toAuthorLabel(),
        category = primaryCategory,
        summary = summary,
    )

internal fun CachedPaper.toPaperUi(summary: String): PaperUiModel =
    PaperUiModel(
        id = id,
        title = title,
        authors = authors.toAuthorLabel(),
        category = primaryCategory ?: "Uncategorized",
        summary = summary,
    )

internal fun List<String>.toAuthorLabel(): String =
    when {
        isEmpty() -> "Unknown authors"
        size <= MAX_VISIBLE_AUTHORS -> joinToString()
        else -> take(MAX_VISIBLE_AUTHORS).joinToString() + " et al."
    }

internal fun String.toSummaryPreview(): String {
    val normalized = trim().replace(Regex("\\s+"), " ")
    return if (normalized.length <= SUMMARY_PREVIEW_LENGTH) {
        normalized
    } else {
        normalized.take(SUMMARY_PREVIEW_LENGTH).trimEnd() + "..."
    }
}

internal fun String.toSourceMatchStatus(): SourceMatchUiStatus =
    when (this) {
        "matched" -> SourceMatchUiStatus.MATCHED
        "partial" -> SourceMatchUiStatus.PARTIAL
        "unmatched" -> SourceMatchUiStatus.UNMATCHED
        "insufficient_evidence" -> SourceMatchUiStatus.INSUFFICIENT_EVIDENCE
        else -> SourceMatchUiStatus.NOT_CHECKED
    }

internal fun String.toDateLabel(): String =
    runCatching { Instant.parse(this).toDateLabel() }
        .getOrDefault("Backend briefing")

internal fun Instant.toDateLabel(): String = DATE_FORMATTER.format(this)

internal fun String.toEpochMillisOrNow(): Long =
    runCatching { Instant.parse(this).toEpochMilli() }
        .getOrDefault(System.currentTimeMillis())

internal fun sourceUrl(arxivId: String): String = "https://arxiv.org/abs/$arxivId"

internal fun disclosure(
    origin: ContentOrigin,
    message: String,
): ContentDisclosureUiModel = ContentDisclosureUiModel(origin, message)

private const val MAX_VISIBLE_AUTHORS = 3
private const val SUMMARY_PREVIEW_LENGTH = 240
private val DATE_FORMATTER: DateTimeFormatter =
    DateTimeFormatter.ofPattern("MMM d, uuuu").withZone(ZoneId.systemDefault())
