package com.mneme.app.ui

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PaperShareIntentTest {
    @Test
    fun shareIntentCarriesThePaperSpecificPayload() {
        val intent = paperShareIntent(PAPER_TITLE, SHARE_TEXT)

        assertEquals(Intent.ACTION_SEND, intent.action)
        assertEquals("text/plain", intent.type)
        assertEquals(PAPER_TITLE, intent.getStringExtra(Intent.EXTRA_SUBJECT))
        assertEquals(SHARE_TEXT, intent.getStringExtra(Intent.EXTRA_TEXT))
    }

    private companion object {
        const val PAPER_TITLE = "Repository paper"
        const val SHARE_TEXT =
            "Repository paper\n" +
                "https://arxiv.org/abs/2401.12345"
    }
}
