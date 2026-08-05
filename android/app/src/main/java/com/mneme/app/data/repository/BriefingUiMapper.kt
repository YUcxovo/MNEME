package com.mneme.app.data.repository

import com.mneme.app.data.local.CachedBriefing
import com.mneme.app.data.network.DigestDto
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.DigestUiModel
import java.time.Instant

internal fun DigestDto.toBriefing(
    interests: List<String>,
    disclosure: ContentDisclosureUiModel,
): BriefingUiModel {
    val orderedEntries = entries.sortedBy { it.rank }
    return BriefingUiModel(
        digest =
            DigestUiModel(
                id = id,
                title = title(),
                summary = description(),
                dateLabel = generatedAt.toDateLabel(),
            ),
        disclosure = disclosure,
        interests = interests,
        papers =
            orderedEntries.map { entry ->
                entry.paper.toPaperUi(
                    summary =
                        entry.recommendationReason.ifBlank {
                            entry.paper.abstract.toSummaryPreview()
                        },
                )
            },
    )
}

internal fun CachedBriefing.toBriefing(): BriefingUiModel =
    toBriefing(
        message =
            "Updates are temporarily unavailable. Showing your saved briefing " +
                "from ${Instant.ofEpochMilli(refreshedAtEpochMillis).toDateLabel()}.",
    )

internal fun CachedBriefing.toRestoredBriefing(): BriefingUiModel =
    toBriefing(
        message =
            "Showing your saved briefing while checking for updates.",
    )

private fun CachedBriefing.toBriefing(message: String): BriefingUiModel =
    BriefingUiModel(
        digest =
            DigestUiModel(
                id = digest.id,
                title = digest.title,
                summary = description,
                dateLabel = Instant.ofEpochMilli(digest.generatedAtEpochMillis).toDateLabel(),
            ),
        disclosure =
            disclosure(
                origin = ContentOrigin.CACHED_BACKEND,
                message = message,
            ),
        interests = interests,
        papers =
            papers.map { paper ->
                paper.toPaperUi(
                    summary =
                        recommendationReasons[paper.id]
                            ?: paper.abstractText.toSummaryPreview(),
                )
            },
    )

private fun DigestDto.title(): String =
    when (digestType) {
        "weekly" -> "Weekly research briefing"
        "manual" -> "Research briefing for your current topics"
        else -> "Research briefing"
    }

private fun DigestDto.description(): String =
    when (entries.size) {
        0 -> "No papers are available for this briefing yet."
        1 -> "One paper prepared for this briefing."
        else -> "${entries.size} papers prepared for this briefing."
    }
