package com.mneme.app.data.demo

import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.DigestUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.PaperUiModel
import com.mneme.app.ui.model.QaUiModel
import com.mneme.app.ui.model.SourceUiModel

interface SkeletalContentRepository {
    fun briefing(): BriefingUiModel

    fun paper(paperId: String): PaperDetailUiModel?

    fun qa(paperId: String): QaUiModel?
}

object SeededSkeletalContentRepository : SkeletalContentRepository {
    const val PAPER_ID = "1706.03762"

    private const val DISCLOSURE =
        "Controlled demo data from the versioned repository fixture. No live model call is made."

    private val source =
        SourceUiModel(
            label = "Attention Is All You Need (arXiv:1706.03762)",
            location = "Model Architecture",
            url = "https://arxiv.org/abs/1706.03762",
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

    private val detail =
        PaperDetailUiModel(
            paper = paper,
            disclosure = DISCLOSURE,
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
            source = source,
        )

    private val qa =
        QaUiModel(
            paperId = PAPER_ID,
            question =
                "What mechanism does the Transformer use instead of recurrence and convolutions?",
            answer =
                "The Transformer relies on attention mechanisms, including multi-head " +
                    "self-attention, to model dependencies without recurrent or convolutional " +
                    "sequence layers.",
            disclosure = DISCLOSURE,
            source = source,
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
            disclosure = DISCLOSURE,
            interests =
                listOf(
                    "Natural language processing",
                    "Efficient models",
                    "Research agents",
                ),
            papers = listOf(paper),
        )

    override fun briefing(): BriefingUiModel = briefing

    override fun paper(paperId: String): PaperDetailUiModel? = detail.takeIf { it.paper.id == paperId }

    override fun qa(paperId: String): QaUiModel? = qa.takeIf { it.paperId == paperId }
}
