package com.mneme.app.evaluation

import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.TextView
import androidx.activity.ComponentActivity
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PreferencesDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext

/**
 * Benchmark-variant-only entry point that prepares a deterministic briefing through the
 * production Room database and cache implementation.
 */
class BenchmarkCacheSeedActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val result =
            runCatching {
                runBlocking { seedBenchmarkCache() }
            }
        val status =
            TextView(this).apply {
                text =
                    if (result.isSuccess) {
                        "Benchmark cache ready"
                    } else {
                        "Benchmark cache seed failed"
                    }
                contentDescription =
                    if (result.isSuccess) {
                        READY_CONTENT_DESCRIPTION
                    } else {
                        ERROR_CONTENT_DESCRIPTION
                    }
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
            }
        setContentView(status)
        result.exceptionOrNull()?.let { error ->
            Log.e(LOG_TAG, "Unable to seed the benchmark cache.", error)
        }
    }

    private suspend fun seedBenchmarkCache() =
        withContext(Dispatchers.IO) {
            val database = MnemeDatabase.create(applicationContext)
            try {
                database.clearAllTables()
                val cache = RoomSkeletalCache(database, MnemeApiClient.json)
                cache.storeBriefing(
                    preferences = benchmarkPreferences(),
                    digest = benchmarkDigest(),
                    refreshedAtEpochMillis = BENCHMARK_TIME_MILLIS,
                )
                val cached = checkNotNull(cache.getBriefing())
                check(cached.papers.map { it.id } == (1..PAPER_COUNT).map(::benchmarkPaperId))
                check(cached.interests == BENCHMARK_TOPICS)
            } finally {
                database.close()
            }
        }

    private companion object {
        const val LOG_TAG = "BenchmarkCacheSeed"
        const val READY_CONTENT_DESCRIPTION = "benchmark-cache-seed-ready"
        const val ERROR_CONTENT_DESCRIPTION = "benchmark-cache-seed-error"
    }
}

private const val PAPER_COUNT = 5
private const val BENCHMARK_TIME = "2026-07-29T00:00:00Z"
private const val BENCHMARK_TIME_MILLIS = 1_785_283_200_000L

private val BENCHMARK_TOPICS =
    listOf(
        "mobile research interfaces",
        "scholarly discovery",
    )

private val BENCHMARK_TITLES =
    listOf(
        "Benchmark Paper 1: Mobile Paper Discovery",
        "Benchmark Paper 2: Cached Research Briefings",
        "Benchmark Paper 3: Interactive Citation Graphs",
        "Benchmark Paper 4: Client Event Synchronization",
        "Benchmark Paper 5: Preference-Aware Ranking",
    )

private val BENCHMARK_REASONS =
    listOf(
        "Matches the mobile research interface topic.",
        "Examines reliable local briefing recovery.",
        "Covers interactive scholarly graph navigation.",
        "Studies client-side event delivery.",
        "Relates preferences to ranked paper discovery.",
    )

private fun benchmarkPaperId(index: Int): String = "10000000-0000-4000-8000-${index.toString().padStart(12, '0')}"

private fun benchmarkPaper(index: Int): PaperDto {
    val arxivId = "2607.${10_000 + index}"
    return PaperDto(
        id = benchmarkPaperId(index),
        arxivId = arxivId,
        title = BENCHMARK_TITLES[index - 1],
        authors = listOf("Benchmark Author"),
        abstract =
            "Deterministic benchmark content for Android cache and rendering measurements.",
        primaryCategory = "cs.HC",
        categories = listOf("cs.HC"),
        pdfUrl = "https://arxiv.org/pdf/$arxivId",
        processingStatus = "ready",
        publishedAt = BENCHMARK_TIME,
        updatedAt = BENCHMARK_TIME,
    )
}

private fun benchmarkPreferences(): PreferencesDto =
    PreferencesDto(
        topics = BENCHMARK_TOPICS,
        followedAuthors = emptyList(),
        modelVersion = 1,
        updatedAt = BENCHMARK_TIME,
    )

private fun benchmarkDigest(): DigestDto =
    DigestDto(
        id = "benchmark-cached-five-paper-digest",
        digestType = "manual",
        generatedAt = BENCHMARK_TIME,
        entries =
            (1..PAPER_COUNT).map { index ->
                DigestEntryDto(
                    paper = benchmarkPaper(index),
                    rank = index,
                    relevanceScore = 1.0 - index * 0.1,
                    recommendationReason = BENCHMARK_REASONS[index - 1],
                )
            },
    )
