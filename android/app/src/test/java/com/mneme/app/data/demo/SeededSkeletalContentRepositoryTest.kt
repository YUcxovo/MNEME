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
        assertTrue(graph?.disclosure?.message?.contains("not a claim about real citations") == true)
        requireNotNull(graph)
        assertEquals(ControlledCitationGraphFixture.NODE_COUNT, graph.nodes.size)
        assertEquals(ControlledCitationGraphFixture.EDGE_COUNT, graph.edges.size)
        assertEquals(
            graph.nodes.size,
            graph.nodes
                .map { it.id }
                .toSet()
                .size,
        )
        assertTrue(
            graph.nodes
                .mapNotNull { it.clusterId }
                .toSet()
                .size >= 4,
        )
        assertTrue(
            graph.nodes
                .mapNotNull { it.category }
                .toSet()
                .size >= 5,
        )
        assertTrue(graph.edges.any { it.source == graph.centerId })
        assertTrue(graph.edges.any { it.target == graph.centerId })
        val nodeIds = graph.nodes.mapTo(mutableSetOf()) { it.id }
        assertTrue(graph.edges.all { it.source in nodeIds && it.target in nodeIds })
        assertTrue(graph.nodes.all { repository.paper(it.id) != null })
        assertNotNull(repository.paper(SeededSkeletalContentRepository.DEEP_GRAPH_PAPER_ID))
    }

    @Test
    fun unknownPaper_hasNoSeededDetailOrAnswer() {
        val repository = SeededSkeletalContentRepository

        assertNull(repository.paper("unknown"))
        assertNull(repository.qa("unknown", "What does this paper claim?"))
        assertNull(repository.graph("unknown"))
    }
}
