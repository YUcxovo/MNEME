package com.mneme.app.data.local

import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.concurrent.TimeUnit

class OfflineCachePolicyTest {
    @Test
    fun cutoffs_keepRecentContentLongerThanOpenedPaperHistory() {
        val now = TimeUnit.DAYS.toMillis(100)

        assertEquals(
            TimeUnit.DAYS.toMillis(86),
            OfflineCachePolicy.recentContentCutoff(now),
        )
        assertEquals(
            TimeUnit.DAYS.toMillis(70),
            OfflineCachePolicy.openedPaperCutoff(now),
        )
    }
}
