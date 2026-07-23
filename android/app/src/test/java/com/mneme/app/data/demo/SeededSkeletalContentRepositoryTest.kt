package com.mneme.app.data.demo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SeededSkeletalContentRepositoryTest {
    @Test
    fun transformerFixture_providesOneInspectablePaperPath() {
        val repository = SeededSkeletalContentRepository
        val briefing = repository.briefing()
        val paper = repository.paper(SeededSkeletalContentRepository.PAPER_ID)
        val question = "How does attention replace recurrent sequence processing?"
        val qa = repository.qa(SeededSkeletalContentRepository.PAPER_ID, question)
        val graph = repository.graph(SeededSkeletalContentRepository.PAPER_ID)

        assertEquals(1, briefing.papers.size)
        assertEquals(SeededSkeletalContentRepository.PAPER_ID, briefing.papers.single().id)
        assertNotNull(paper)
        assertNotNull(qa)
        assertNotNull(graph)
        assertEquals(question, qa?.question)
        assertTrue(qa?.answer?.contains("cannot generate a new answer") == true)
        assertEquals("Model Architecture", qa?.sources?.single()?.location)
        assertTrue(briefing.disclosure.message.contains("No live backend or model call"))
        assertTrue(graph?.disclosure?.message?.contains("not a claim about a real citation") == true)
        assertNotNull(repository.paper(SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID))
    }

    @Test
    fun unknownPaper_hasNoSeededDetailOrAnswer() {
        val repository = SeededSkeletalContentRepository

        assertNull(repository.paper("unknown"))
        assertNull(repository.qa("unknown", "What does this paper claim?"))
        assertNull(repository.graph("unknown"))
    }
}
