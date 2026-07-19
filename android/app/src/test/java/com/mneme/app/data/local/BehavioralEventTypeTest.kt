package com.mneme.app.data.local

import org.junit.Assert.assertEquals
import org.junit.Test

class BehavioralEventTypeTest {
    @Test
    fun eventTypes_matchTheMilestoneThreeBehaviorSignals() {
        assertEquals(
            setOf("open", "save", "skip", "share", "question", "time_spent"),
            BehavioralEventType.entries.map { it.name.lowercase() }.toSet(),
        )
    }
}
