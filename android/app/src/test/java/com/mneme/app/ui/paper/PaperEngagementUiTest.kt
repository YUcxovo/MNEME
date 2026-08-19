package com.mneme.app.ui.paper

import com.mneme.app.R
import com.mneme.app.ui.EventRecordingStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PaperEngagementUiTest {
    @Test
    fun failedShareTelemetryKeepsAccurateChooserFeedback() {
        val status = EventRecordingStatus.FAILED

        assertEquals(R.string.share_recorded, status.feedbackRes(isShare = true))
        assertFalse(status.feedbackIsFailure(isShare = true))
    }

    @Test
    fun failedSaveStillOffersAVisibleRetry() {
        val status = EventRecordingStatus.FAILED

        assertEquals(R.string.save_record_failed, status.feedbackRes())
        assertTrue(status.feedbackIsFailure())
    }
}
