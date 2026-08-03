package com.mneme.app.ui

import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.MnemeRemoteDataSource
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PreferencesDto
import com.mneme.app.data.network.RemoteResource
import com.mneme.app.data.network.SummaryDto
import java.io.IOException
import java.lang.reflect.Proxy
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.Continuation
import kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED

internal const val REQUEST_ID = 81L
internal const val EXTERNAL_EVENT_ID = "77777777-7777-4777-8777-777777777777"
internal const val FIXED_TIME = 1_800_000_000_000L
internal const val UI_TIMEOUT_MILLIS = 10_000L

internal val TARGET_PAPER =
    paper(
        id = "8f0a1d3b-cc41-43f0-97c2-c175341ef07c",
        arxivId = "2401.12345",
        title = "Repository-resolved deep-link paper",
    )
internal val BRIEFING_PAPER =
    paper(
        id = "e63ff7fe-4f7c-45eb-a188-df825de81f4f",
        arxivId = "2401.00001",
        title = "Briefing paper with a different identifier",
    )
internal val BRIEFING_PREFERENCES =
    PreferencesDto(
        topics = listOf("software engineering"),
        followedAuthors = emptyList(),
        modelVersion = 1,
        updatedAt = "2026-08-04T00:00:00Z",
    )
internal val BRIEFING_DIGEST =
    DigestDto(
        id = "7c4d8239-0c58-497c-b0d5-8a99f412c282",
        digestType = "manual",
        generatedAt = "2026-08-04T00:00:00Z",
        entries =
            listOf(
                DigestEntryDto(
                    paper = BRIEFING_PAPER,
                    rank = 1,
                    relevanceScore = 0.8,
                    recommendationReason = "Matches the configured topic.",
                ),
            ),
    )
internal val TARGET_SUMMARY =
    SummaryDto(
        paperId = TARGET_PAPER.id,
        status = "ready",
        tldr = "A paper loaded through the normal repository path.",
        keyClaims = listOf("The requested identifier determines the loaded paper."),
        methodology = "Repository integration test.",
        limitations = "Controlled network availability.",
        sourceMatchStatus = "matched",
    )

@Suppress("UNCHECKED_CAST")
internal fun paperRemote(networkAvailable: AtomicBoolean): MnemeRemoteDataSource =
    Proxy.newProxyInstance(
        MnemeRemoteDataSource::class.java.classLoader,
        arrayOf(MnemeRemoteDataSource::class.java),
    ) { proxy, method, arguments ->
        when (method.name) {
            "getPaper" ->
                if (networkAvailable.get()) {
                    TARGET_PAPER
                } else {
                    offlineResult(arguments)
                }
            "getPaperSummary" -> RemoteResource.Ready(TARGET_SUMMARY)
            "toString" -> "PaperRemote(available=${networkAvailable.get()})"
            "hashCode" -> System.identityHashCode(proxy)
            "equals" -> proxy === arguments?.firstOrNull()
            else -> offlineResult(arguments)
        }
    } as MnemeRemoteDataSource

@Suppress("UNCHECKED_CAST")
private fun offlineResult(arguments: Array<out Any?>?): Any {
    val continuation = requireNotNull(arguments).last() as Continuation<Any?>
    continuation.resumeWith(Result.failure(IOException("controlled offline state")))
    return COROUTINE_SUSPENDED
}

private fun paper(
    id: String,
    arxivId: String,
    title: String,
): PaperDto =
    PaperDto(
        id = id,
        arxivId = arxivId,
        title = title,
        authors = listOf("Mneme Test Author"),
        abstract = "Repository-backed paper metadata used by the deep-link integration test.",
        primaryCategory = "cs.SE",
        categories = listOf("cs.SE"),
        pdfUrl = "https://arxiv.org/pdf/$arxivId",
        processingStatus = "ready",
        publishedAt = "2026-08-01T00:00:00Z",
        updatedAt = "2026-08-02T00:00:00Z",
    )
