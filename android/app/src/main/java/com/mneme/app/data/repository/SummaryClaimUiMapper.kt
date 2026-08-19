package com.mneme.app.data.repository

import com.mneme.app.data.network.ClaimProvenanceDto
import com.mneme.app.data.network.SourcedClaimDto
import com.mneme.app.data.network.SummaryDto
import com.mneme.app.ui.model.ClaimProvenanceUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SummaryClaimUiModel
import kotlinx.serialization.SerializationException

internal fun SummaryDto.toUiClaims(): List<SummaryClaimUiModel> {
    if (claims.isEmpty()) {
        return keyClaims.map { claim ->
            SummaryClaimUiModel(
                text = claim,
                matchStatus = SourceMatchUiStatus.NOT_CHECKED,
            )
        }
    }
    if (claims.map(SourcedClaimDto::text) != keyClaims) {
        throw SerializationException("Summary claims do not match the ordered key claims.")
    }
    return claims.map(SourcedClaimDto::toUiClaim)
}

private fun SourcedClaimDto.toUiClaim(): SummaryClaimUiModel {
    val normalizedText = text.trim()
    if (normalizedText.isEmpty()) {
        throw SerializationException("Summary claims cannot be blank.")
    }
    val validatedSource = source?.toUiSource()?.takeIf { matched }
    return SummaryClaimUiModel(
        text = normalizedText,
        matchStatus =
            if (validatedSource == null) {
                SourceMatchUiStatus.UNMATCHED
            } else {
                SourceMatchUiStatus.MATCHED
            },
        source = validatedSource,
    )
}

private fun ClaimProvenanceDto.toUiSource(): ClaimProvenanceUiModel? {
    val normalizedChunkId = chunkId.trim()
    val normalizedExcerpt = excerpt.trim()
    if (normalizedChunkId.isEmpty() || chunkIndex < 0 || normalizedExcerpt.isEmpty()) {
        return null
    }
    val normalizedStart = pageStart?.takeIf { page -> page > 0 }
    val normalizedEnd = pageEnd?.takeIf { page -> page > 0 }
    val validPageRange =
        normalizedStart == null || normalizedEnd == null || normalizedEnd >= normalizedStart
    return ClaimProvenanceUiModel(
        chunkId = normalizedChunkId,
        chunkIndex = chunkIndex,
        sectionTitle = sectionTitle?.trim()?.takeIf(String::isNotEmpty),
        pageStart = normalizedStart.takeIf { validPageRange },
        pageEnd = normalizedEnd.takeIf { validPageRange },
        excerpt = normalizedExcerpt,
    )
}
