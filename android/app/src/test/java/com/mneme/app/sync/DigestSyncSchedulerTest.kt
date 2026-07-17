package com.mneme.app.sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DigestSyncSchedulerTest {
    @Test
    fun periodicPolicy_hasStableUniqueNameAndSafeIntervals() {
        assertEquals("digest-periodic-sync", DigestSyncScheduler.UNIQUE_WORK_NAME)
        assertTrue(DigestSyncScheduler.REPEAT_INTERVAL_HOURS >= 1)
        assertTrue(DigestSyncScheduler.BACKOFF_DELAY_SECONDS >= 10)
    }
}
