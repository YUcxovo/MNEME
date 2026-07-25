package com.mneme.app.data.behavior

import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.DigestUiModel
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel

internal const val EVENT_TRACE_PAPER_ID = "2d3f275d-2f4f-4144-a9fd-a2cbe8f12c88"
internal const val EVENT_TRACE_PAPER_TITLE = "Controlled E4 event paper"
internal const val EVENT_TRACE_QUESTION = "Which interaction is recorded?"
internal const val EVENT_TRACE_TIME = 1_782_000_000_000L

internal class EventTraceRepository : SkeletalDataRepository {
    override suspend fun restoreBriefing(): BriefingUiModel = briefing()

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel = briefing()

    override suspend fun loadBriefing(): BriefingUiModel = briefing()

    override suspend fun loadPaper(paperId: String): PaperContentResult = PaperContentResult.Ready(paperDetail())

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult = loadPaper(paperId)

    override suspend fun askQuestion(
        paperId: String,
        question: String,
    ): QaUiModel =
        QaUiModel(
            paperId = paperId,
            question = question,
            answer = "A controlled response used only to complete the visible interaction.",
            disclosure = disclosure(),
            sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
            sources = listOf(source()),
        )

    override suspend fun loadGraph(paperId: String): GraphUiModel = error("Graph is outside this event trace.")
}

private fun briefing(): BriefingUiModel =
    BriefingUiModel(
        digest =
            DigestUiModel(
                id = "e4-digest",
                title = "Controlled E4 briefing",
                summary = "One paper for the device event trace.",
                dateLabel = "25 Jul 2026",
            ),
        disclosure = disclosure(),
        interests = listOf("mobile systems"),
        papers = listOf(paper()),
    )

private fun paperDetail(): PaperDetailUiModel =
    PaperDetailUiModel(
        paper = paper(),
        disclosure = disclosure(),
        abstractText = "A controlled paper detail for the E4 device trace.",
        keyClaims = listOf("Visible actions enter the production tracker."),
        methodology = null,
        limitation = "The HTTP endpoint is controlled, not the live backend.",
        sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
        source = source(),
    )

private fun paper(): PaperUiModel =
    PaperUiModel(
        id = EVENT_TRACE_PAPER_ID,
        title = EVENT_TRACE_PAPER_TITLE,
        authors = "E4 fixture",
        category = "cs.SE",
        summary = "A controlled paper for event-boundary testing.",
    )

private fun source(): SourceUiModel =
    SourceUiModel(
        label = "Controlled source",
        location = "Fixture",
        url = "https://arxiv.org/abs/1706.03762",
    )

private fun disclosure(): ContentDisclosureUiModel =
    ContentDisclosureUiModel(
        origin = ContentOrigin.CONTROLLED_FIXTURE,
        message = "Controlled E4 device integration fixture.",
    )
