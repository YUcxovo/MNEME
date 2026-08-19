package com.mneme.app.data.local

import org.junit.Assert.assertEquals
import org.junit.Test

class BehavioralEventTypeTest {
    @Test
    fun eventTypes_matchTheMilestoneThreeBehaviorSignals() {
        assertEquals(
            setOf(
                "paper_impression",
                "paper_opened",
                "paper_saved",
                "paper_skipped",
                "paper_shared",
                "question_asked",
                "digest_dismissed",
            ),
            BehavioralEventType.entries.map(BehavioralEventType::wireValue).toSet(),
        )
    }
}
