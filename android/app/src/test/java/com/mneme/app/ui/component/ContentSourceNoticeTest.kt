package com.mneme.app.ui.component

import com.mneme.app.R
import com.mneme.app.ui.model.ContentOrigin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ContentSourceNoticeTest {
    @Test
    fun liveContentHasNoSourceBadge() {
        assertNull(ContentOrigin.LIVE_BACKEND.noticeLabel())
    }

    @Test
    fun cachedAndControlledContentHaveExplicitLabels() {
        assertEquals(R.string.content_source_cached, ContentOrigin.CACHED_BACKEND.noticeLabel())
        assertEquals(R.string.controlled_demo_title, ContentOrigin.CONTROLLED_FIXTURE.noticeLabel())
    }
}
