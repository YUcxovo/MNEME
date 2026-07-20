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
        val qa = repository.qa(SeededSkeletalContentRepository.PAPER_ID)

        assertEquals(1, briefing.papers.size)
        assertEquals(SeededSkeletalContentRepository.PAPER_ID, briefing.papers.single().id)
        assertNotNull(paper)
        assertNotNull(qa)
        assertTrue(qa?.answer?.contains("multi-head self-attention") == true)
        assertEquals("Model Architecture", qa?.source?.location)
        assertTrue(briefing.disclosure.contains("No live model call"))
    }

    @Test
    fun unknownPaper_hasNoSeededDetailOrAnswer() {
        val repository = SeededSkeletalContentRepository

        assertNull(repository.paper("unknown"))
        assertNull(repository.qa("unknown"))
    }
}
