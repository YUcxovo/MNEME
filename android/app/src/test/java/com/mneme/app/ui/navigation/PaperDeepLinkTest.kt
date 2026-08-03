package com.mneme.app.ui.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.net.URI

class PaperDeepLinkTest {
    @Test
    fun buildsUriFromCanonicalBackendPaperId() {
        assertEquals(
            URI("mneme://paper/$PAPER_ID"),
            PaperDeepLink.buildUri(PAPER_ID),
        )
    }

    @Test
    fun rejectsNonCanonicalPaperIdWhenBuildingUri() {
        listOf(
            PAPER_ID.uppercase(),
            PAPER_ID.replace("-", ""),
            " $PAPER_ID",
            "not-a-uuid",
            "",
        ).forEach { invalidPaperId ->
            assertThrows(IllegalArgumentException::class.java) {
                PaperDeepLink.buildUri(invalidPaperId)
            }
        }
    }

    @Test
    fun parsesExactPaperDeepLink() {
        assertEquals(
            PAPER_ID,
            PaperDeepLink.parseUri("mneme://paper/$PAPER_ID"),
        )
        assertEquals(
            PAPER_ID,
            PaperDeepLink.parseUri(URI("mneme://paper/$PAPER_ID")),
        )
    }

    @Test
    fun rejectsWrongSchemeOrHost() {
        listOf(
            "https://paper/$PAPER_ID",
            "MNEME://paper/$PAPER_ID",
            "mneme://papers/$PAPER_ID",
            "mneme://PAPER/$PAPER_ID",
            "mneme://user@paper/$PAPER_ID",
            "mneme://paper:443/$PAPER_ID",
        ).forEach { invalidUri ->
            assertNull(PaperDeepLink.parseUri(invalidUri))
        }
    }

    @Test
    fun rejectsMissingOrNonSinglePath() {
        listOf(
            "mneme://paper",
            "mneme://paper/",
            "mneme://paper/$PAPER_ID/",
            "mneme://paper/extra/$PAPER_ID",
            "mneme://paper/$PAPER_ID/extra",
        ).forEach { invalidUri ->
            assertNull(PaperDeepLink.parseUri(invalidUri))
        }
    }

    @Test
    fun rejectsQueryAndFragmentEvenWhenEmpty() {
        listOf(
            "mneme://paper/$PAPER_ID?ref=share",
            "mneme://paper/$PAPER_ID?",
            "mneme://paper/$PAPER_ID#details",
            "mneme://paper/$PAPER_ID#",
        ).forEach { invalidUri ->
            assertNull(PaperDeepLink.parseUri(invalidUri))
        }
    }

    @Test
    fun rejectsMalformedEncodedAndNonCanonicalIdsWhenParsing() {
        listOf(
            "mneme://paper/${PAPER_ID.uppercase()}",
            "mneme://paper/${PAPER_ID.replace("-", "")}",
            "mneme://paper/not-a-uuid",
            "mneme://paper/%61aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "mneme://paper/$PAPER_ID%2Fextra",
            "mneme://paper/[invalid",
            "",
        ).forEach { invalidUri ->
            assertNull(PaperDeepLink.parseUri(invalidUri))
        }
    }

    @Test
    fun buildsShareTextFromCallerProvidedPaperValues() {
        assertEquals(
            "A Real Paper Title\nmneme://paper/$PAPER_ID\n$ARXIV_URL",
            PaperDeepLink.buildShareText(
                title = "A Real Paper Title",
                paperId = PAPER_ID,
                arxivUrl = ARXIV_URL,
            ),
        )
    }

    @Test
    fun shareTextUsesEachPaperValuesWithoutAPlaceholderMapping() {
        val otherPaperId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        val otherArxivUrl = "https://arxiv.org/abs/2608.54321"

        assertEquals(
            "Another Paper\nmneme://paper/$otherPaperId\n$otherArxivUrl",
            PaperDeepLink.buildShareText(
                title = " Another Paper ",
                paperId = otherPaperId,
                arxivUrl = " $otherArxivUrl ",
            ),
        )
    }

    @Test
    fun rejectsShareTextWithoutRealCallerProvidedMetadata() {
        assertThrows(IllegalArgumentException::class.java) {
            PaperDeepLink.buildShareText(" ", PAPER_ID, ARXIV_URL)
        }
        assertThrows(IllegalArgumentException::class.java) {
            PaperDeepLink.buildShareText("Paper", PAPER_ID, " ")
        }
        assertThrows(IllegalArgumentException::class.java) {
            PaperDeepLink.buildShareText("Paper", "not-a-uuid", ARXIV_URL)
        }
    }

    private companion object {
        const val PAPER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        const val ARXIV_URL = "https://arxiv.org/abs/2608.12345"
    }
}
