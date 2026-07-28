package com.mneme.app.ui

import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.repository.PaperContentResult
import com.mneme.app.data.repository.SkeletalDataRepository
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.QaUiModel
import kotlinx.serialization.SerializationException
import java.util.ArrayDeque

internal const val E4_PAPER_TITLE = "Attention Is All You Need"
internal const val E4_JOB_ID = "e4-paper-job"

internal class ScenarioRepository(
    private val restoredBriefing: BriefingUiModel? = null,
    private val refreshedBriefing: BriefingUiModel = restoredBriefing ?: e4Briefing(),
    private val seedBriefing: BriefingUiModel = e4Briefing(ContentOrigin.LIVE_BACKEND, "Seed ready."),
    private val invalidStoredBriefing: Boolean = false,
    paperResults: List<PaperContentResult> =
        listOf(
            PaperContentResult.Ready(
                requireNotNull(
                    SeededSkeletalContentRepository.paper(SeededSkeletalContentRepository.PAPER_ID),
                ),
            ),
        ),
) : SkeletalDataRepository {
    private val paperResults = ArrayDeque(paperResults)
    val refreshedJobIds = mutableListOf<String>()
    var submittedSeed: String? = null

    override suspend fun restoreBriefing(): BriefingUiModel? {
        if (invalidStoredBriefing) {
            throw SerializationException("invalid stored digest")
        }
        return restoredBriefing
    }

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel {
        submittedSeed = arxivReference
        return seedBriefing
    }

    override suspend fun loadBriefing(): BriefingUiModel = refreshedBriefing

    override suspend fun updateInterests(topics: List<String>): BriefingUiModel = refreshedBriefing.copy(interests = topics)

    override suspend fun loadPaper(paperId: String): PaperContentResult = paperResults.removeFirst()

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult {
        refreshedJobIds += jobId
        return paperResults.removeFirst()
    }

    override suspend fun askQuestion(
        paperId: String,
        question: String,
    ): QaUiModel = error("Question answering is outside the state matrix.")

    override suspend fun loadGraph(paperId: String): GraphUiModel = error("Graph loading is outside the state matrix.")
}

internal fun e4Processing(stage: String): PaperContentResult.Processing =
    PaperContentResult.Processing(
        paperId = SeededSkeletalContentRepository.PAPER_ID,
        jobId = E4_JOB_ID,
        stage = stage,
    )

internal fun e4Briefing(
    origin: ContentOrigin = ContentOrigin.CONTROLLED_FIXTURE,
    message: String = "Controlled state fixture.",
    fivePapers: Boolean = false,
): BriefingUiModel {
    val source = SeededSkeletalContentRepository.briefing()
    val papers =
        if (fivePapers) {
            (1..5).map { index ->
                source.papers.single().copy(
                    id = "state-paper-$index",
                    title = if (index == 1) E4_PAPER_TITLE else "Controlled paper $index",
                )
            }
        } else {
            source.papers
        }
    return source.copy(
        disclosure =
            ContentDisclosureUiModel(
                origin = origin,
                message = message,
            ),
        papers = papers,
    )
}
