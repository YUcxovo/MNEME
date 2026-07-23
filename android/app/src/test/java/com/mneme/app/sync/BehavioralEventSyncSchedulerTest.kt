package com.mneme.app.sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BehavioralEventSyncSchedulerTest {
    @Test
    fun retryPolicy_hasStableUniqueNameAndSafeBackoff() {
        assertEquals("behavioral-event-sync", BehavioralEventSyncScheduler.UNIQUE_WORK_NAME)
        assertTrue(BehavioralEventSyncScheduler.BACKOFF_DELAY_SECONDS >= 10)
    }
}
