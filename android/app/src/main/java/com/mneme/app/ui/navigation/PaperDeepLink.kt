package com.mneme.app.ui.navigation

import java.net.URI
import java.net.URISyntaxException
import java.util.UUID

/** The application-owned URI contract for opening a paper by its backend identifier. */
object PaperDeepLink {
    private const val SCHEME = "mneme"
    private const val HOST = "paper"

    /** Builds `mneme://paper/<paper-id>` from a canonical backend UUID. */
    fun buildUri(paperId: String): URI {
        requireCanonicalPaperId(paperId)
        return URI(SCHEME, HOST, "/$paperId", null)
    }

    /** Returns the backend paper UUID when [rawUri] exactly matches this contract. */
    fun parseUri(rawUri: String): String? =
        try {
            parseUri(URI(rawUri))
        } catch (_: URISyntaxException) {
            null
        }

    /** Returns the backend paper UUID when [uri] exactly matches this contract. */
    fun parseUri(uri: URI): String? {
        val rawPath = uri.rawPath
        return if (
            !uri.hasExactContractEnvelope() ||
            rawPath == null ||
            !rawPath.isSinglePaperPath()
        ) {
            null
        } else {
            rawPath.removePrefix("/").takeIf(::isCanonicalPaperId)
        }
    }

    /** Builds public share text from the selected paper's title and arXiv URL. */
    fun buildShareText(
        title: String,
        arxivUrl: String,
    ): String {
        val normalizedTitle = title.trim()
        val normalizedArxivUrl = arxivUrl.trim()
        require(normalizedTitle.isNotEmpty()) { "Paper title must not be blank." }
        require(normalizedArxivUrl.isNotEmpty()) { "The arXiv URL must not be blank." }
        return "$normalizedTitle\n$normalizedArxivUrl"
    }

    private fun requireCanonicalPaperId(paperId: String) {
        require(isCanonicalPaperId(paperId)) {
            "Paper ID must be a canonical lowercase UUID."
        }
    }

    private fun isCanonicalPaperId(paperId: String): Boolean =
        try {
            UUID.fromString(paperId).toString() == paperId
        } catch (_: IllegalArgumentException) {
            false
        }

    private fun URI.hasExactContractEnvelope(): Boolean = hasExactPaperAuthority() && hasNoQueryOrFragment()

    private fun URI.hasExactPaperAuthority(): Boolean = !isOpaque && scheme == SCHEME && rawAuthority == HOST

    private fun URI.hasNoQueryOrFragment(): Boolean = rawQuery == null && rawFragment == null

    private fun String.isSinglePaperPath(): Boolean = startsWith('/') && indexOf('/', startIndex = 1) < 0
}
