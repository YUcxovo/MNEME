package com.mneme.app.data.repository

import com.mneme.app.data.local.CachedPaper
import com.mneme.app.data.network.AnswerDto
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.SummaryDto
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel
import kotlinx.serialization.SerializationException

internal fun PaperDto.toDetail(summary: SummaryDto): PaperDetailUiModel {
    if (summary.paperId != id) {
        throw SerializationException("The summary paper ID does not match the requested paper.")
    }
    return PaperDetailUiModel(
        paper = toPaperUi(summary.tldr),
        disclosure =
            disclosure(
                ContentOrigin.LIVE_BACKEND,
                "Paper details are up to date.",
            ),
        abstractText = abstract,
        keyClaims = summary.keyClaims,
        methodology = summary.methodology,
        limitation = summary.limitations,
        sourceMatchStatus = summary.sourceMatchStatus.toSourceMatchStatus(),
        summaryClaims = summary.toUiClaims(),
        source =
            SourceUiModel(
                label = "$title (arXiv:$arxivId)",
                location = "Source paper",
                url = sourceUrl(arxivId),
            ),
    )
}

internal fun CachedPaper.toCachedDetail(): PaperContentResult.Ready =
    PaperContentResult.Ready(
        summary
            ?.let { cachedSummary ->
                runCatching { toCachedSummaryDetail(cachedSummary) }.getOrNull()
            } ?: toCachedMetadataDetail(),
    )

private fun CachedPaper.toCachedSummaryDetail(summary: SummaryDto): PaperDetailUiModel {
    if (summary.paperId != id) {
        throw SerializationException("The cached summary paper ID does not match its paper.")
    }
    return PaperDetailUiModel(
        paper = toPaperUi(summary.tldr),
        disclosure =
            disclosure(
                ContentOrigin.CACHED_BACKEND,
                "Updates are temporarily unavailable. This saved summary includes its " +
                    "recorded source links.",
            ),
        abstractText = abstractText,
        keyClaims = summary.keyClaims,
        methodology = summary.methodology,
        limitation = summary.limitations,
        sourceMatchStatus = summary.sourceMatchStatus.toSourceMatchStatus(),
        source = paperSource(),
        summaryClaims = summary.toUiClaims(),
    )
}

private fun CachedPaper.toCachedMetadataDetail(): PaperDetailUiModel =
    PaperDetailUiModel(
        paper = toPaperUi(abstractText.toSummaryPreview()),
        disclosure =
            disclosure(
                ContentOrigin.CACHED_BACKEND,
                "Updates are temporarily unavailable. This saved paper has no generated " +
                    "summary yet.",
            ),
        abstractText = abstractText,
        keyClaims = emptyList(),
        methodology = null,
        limitation = null,
        sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
        source = paperSource(),
    )

private fun CachedPaper.paperSource(): SourceUiModel =
    SourceUiModel(
        label = "$title (arXiv:$arxivId)",
        location = "Source paper",
        url = sourceUrl(arxivId),
    )

internal fun AnswerDto.toQa(
    paper: CachedPaper,
    question: String,
    requestedConversationId: String? = null,
): QaUiModel {
    if (citations.any { citation -> citation.paperId != paper.id }) {
        throw SerializationException("A Q&A citation points to a different paper.")
    }
    if (requestedConversationId != null && conversationId != requestedConversationId) {
        throw SerializationException("The backend changed the active Q&A conversation.")
    }
    return QaUiModel(
        paperId = paper.id,
        conversationId = conversationId,
        question = question,
        answer = answer,
        disclosure =
            disclosure(
                ContentOrigin.LIVE_BACKEND,
                "This answer came from the single-paper backend Q&A path. Source matching " +
                    "checks retrieved chunks; it does not claim semantic entailment.",
            ),
        sourceMatchStatus = sourceMatchStatus.toSourceMatchStatus(),
        sources =
            citations
                .map { citation -> citation.toSource(paper) }
                .distinctBy { source -> source.location to source.url },
    )
}

internal fun PaperDto.toCachedPaper(): CachedPaper =
    CachedPaper(
        id = id,
        arxivId = arxivId,
        title = title,
        authors = authors,
        abstractText = abstract,
        primaryCategory = primaryCategory,
        pdfUrl = pdfUrl,
        processingStatus = processingStatus,
        updatedAtEpochMillis = updatedAt.toEpochMillisOrNow(),
    )

private fun com.mneme.app.data.network.CitationDto.toSource(paper: CachedPaper): SourceUiModel {
    val citationArxivId = arxivId ?: paper.arxivId
    return SourceUiModel(
        label = "${paper.title} (arXiv:$citationArxivId)",
        location = sectionTitle.ifBlank { "Paper text" },
        url = sourceUrl(citationArxivId),
        matchStatus =
            if (sourceMatch) {
                SourceMatchUiStatus.MATCHED
            } else {
                SourceMatchUiStatus.UNMATCHED
            },
    )
}
