package com.mneme.app.data.demo

import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentDisclosureUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.DigestUiModel
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.GraphEdgeUiModel
import com.mneme.app.ui.model.GraphNodeUiModel
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceMatchUiStatus
import com.mneme.app.ui.model.SourceUiModel

interface SkeletalContentRepository {
    fun briefing(): BriefingUiModel

    fun paper(paperId: String): PaperDetailUiModel?

    fun qa(
        paperId: String,
        question: String,
    ): QaUiModel?

    fun graph(paperId: String): GraphUiModel?
}

object SeededSkeletalContentRepository : SkeletalContentRepository {
    const val PAPER_ID = "1706.03762"
    const val NEIGHBOR_PAPER_ID = "controlled-neighbor-1"

    private val disclosure =
        ContentDisclosureUiModel(
            origin = ContentOrigin.CONTROLLED_FIXTURE,
            message =
                "Controlled demo data from the versioned repository fixture. " +
                    "No live backend or model call is made.",
        )

    private val source =
        SourceUiModel(
            label = "Attention Is All You Need (arXiv:1706.03762)",
            location = "Model Architecture",
            url = "https://arxiv.org/abs/1706.03762",
            matchStatus = SourceMatchUiStatus.NOT_CHECKED,
        )

    private val paper =
        PaperUiModel(
            id = PAPER_ID,
            title = "Attention Is All You Need",
            authors = "Ashish Vaswani et al.",
            category = "cs.CL",
            summary =
                "The paper introduces the Transformer, a sequence model built around " +
                    "attention instead of recurrent layers.",
        )

    private val neighborPaper =
        PaperUiModel(
            id = NEIGHBOR_PAPER_ID,
            title = "Controlled neighbor paper",
            authors = "Repository renderer fixture",
            category = "cs.AI",
            summary =
                "This paper exists only in the controlled Android fixture for graph navigation tests.",
        )

    private val detail =
        PaperDetailUiModel(
            paper = paper,
            disclosure = disclosure,
            abstractText =
                "The work presents an encoder-decoder architecture that models sequence " +
                    "relationships with attention and position-aware representations.",
            keyClaims =
                listOf(
                    "Multi-head self-attention models dependencies across sequence positions.",
                    "The architecture removes recurrent and convolutional sequence layers.",
                ),
            methodology =
                "The model stacks attention and feed-forward blocks in an encoder-decoder design.",
            limitation =
                "This skeletal view uses one seeded paper and does not measure live retrieval " +
                    "or generation quality.",
            sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
            source = source,
        )

    private val neighborDetail =
        PaperDetailUiModel(
            paper = neighborPaper,
            disclosure = disclosure,
            abstractText =
                "This local fixture has no claim about a real citation relationship or source paper.",
            keyClaims = emptyList(),
            methodology = null,
            limitation = "Use the live backend for real paper and citation data.",
            sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
            source =
                SourceUiModel(
                    label = "No external source in the controlled graph fixture",
                    location = "Android renderer fixture",
                    url = "https://arxiv.org/",
                    matchStatus = SourceMatchUiStatus.NOT_CHECKED,
                ),
        )

    private val qa =
        QaUiModel(
            paperId = PAPER_ID,
            question =
                "What mechanism does the Transformer use instead of recurrence and convolutions?",
            answer =
                "This controlled fixture cannot generate a new answer. It demonstrates the " +
                    "paper-scoped question, answer, and source layout without a live backend " +
                    "or model call.",
            disclosure = disclosure,
            sourceMatchStatus = SourceMatchUiStatus.NOT_CHECKED,
            sources = listOf(source),
        )

    private val briefing =
        BriefingUiModel(
            digest =
                DigestUiModel(
                    id = "skeletal-briefing-1",
                    title = "Research briefing for your seeded interests",
                    summary =
                        "One inspectable paper path prepared for the skeletal product demo.",
                    dateLabel = "Skeletal demo",
                ),
            disclosure = disclosure,
            interests =
                listOf(
                    "Natural language processing",
                    "Efficient models",
                    "Research agents",
                ),
            papers = listOf(paper),
        )

    override fun briefing(): BriefingUiModel = briefing

    override fun paper(paperId: String): PaperDetailUiModel? =
        detail.takeIf { it.paper.id == paperId }
            ?: neighborDetail.takeIf { it.paper.id == paperId }

    override fun qa(
        paperId: String,
        question: String,
    ): QaUiModel? =
        qa
            .takeIf { it.paperId == paperId }
            ?.copy(question = question)

    override fun graph(paperId: String): GraphUiModel? =
        if (paperId == PAPER_ID) {
            GraphUiModel(
                centerId = PAPER_ID,
                nodes =
                    listOf(
                        GraphNodeUiModel(
                            id = PAPER_ID,
                            title = paper.title,
                            category = paper.category,
                            clusterId = "controlled-cluster",
                            rankScore = 1.0,
                        ),
                        GraphNodeUiModel(
                            id = NEIGHBOR_PAPER_ID,
                            title = neighborPaper.title,
                            category = neighborPaper.category,
                            clusterId = "controlled-cluster",
                            rankScore = 0.5,
                        ),
                    ),
                edges =
                    listOf(
                        GraphEdgeUiModel(
                            source = PAPER_ID,
                            target = NEIGHBOR_PAPER_ID,
                            weight = 0.5,
                        ),
                    ),
                algorithmStatus = GraphAlgorithmUiStatus.FALLBACK,
                graphVersion = "controlled-renderer-fixture-v1",
                disclosure =
                    ContentDisclosureUiModel(
                        origin = ContentOrigin.CONTROLLED_FIXTURE,
                        message =
                            "Controlled renderer fixture. Its edge is not a claim about a real citation.",
                    ),
            )
        } else {
            null
        }
}
