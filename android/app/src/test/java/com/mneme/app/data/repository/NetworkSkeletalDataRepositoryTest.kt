package com.mneme.app.data.repository

import com.mneme.app.data.local.CachedBriefing
import com.mneme.app.data.local.CachedPaper
import com.mneme.app.data.local.SkeletalCache
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.network.AnswerDto
import com.mneme.app.data.network.CitationDto
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.DigestEntryDto
import com.mneme.app.data.network.DigestPageDto
import com.mneme.app.data.network.HealthDto
import com.mneme.app.data.network.JobDto
import com.mneme.app.data.network.MnemeRemoteDataSource
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PaperPageDto
import com.mneme.app.data.network.PreferenceUpdateDto
import com.mneme.app.data.network.PreferencesDto
import com.mneme.app.data.network.QUESTION_MAX_LENGTH
import com.mneme.app.data.network.QuestionDto
import com.mneme.app.data.network.RemoteResource
import com.mneme.app.data.network.SummaryDto
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.SourceMatchUiStatus
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class NetworkSkeletalDataRepositoryTest {
    @Test
    fun loadBriefing_mapsRankedLiveDigestAndStoresRoomBoundary() =
        runBlocking {
            val remote = FakeRemote()
            val cache = FakeCache()
            remote.preferences = preferences()
            remote.digestResult =
                RemoteResource.Ready(
                    digest(
                        entries =
                            listOf(
                                entry(paper("paper-2", "Second paper"), rank = 2, reason = "Second reason"),
                                entry(paper("paper-1", "First paper"), rank = 1, reason = "First reason"),
                            ),
                    ),
                )
            val repository = NetworkSkeletalDataRepository(remote, cache) { REFRESHED_AT }

            val briefing = repository.loadBriefing()

            assertEquals(ContentOrigin.LIVE_BACKEND, briefing.disclosure.origin)
            assertEquals(listOf("paper-1", "paper-2"), briefing.papers.map { it.id })
            assertEquals("First reason", briefing.papers.first().summary)
            assertEquals(listOf("retrieval", "mobile systems"), briefing.interests)
            assertEquals(REFRESHED_AT, cache.storedBriefingAt)
            assertEquals("digest-1", cache.storedDigest?.id)
        }

    @Test
    fun loadBriefing_liveFailureUsesExplicitCachedBackendState() =
        runBlocking {
            val remote = FakeRemote().apply { briefingFailure = IOException("offline") }
            val cache = FakeCache().apply { cachedBriefing = cachedBriefing() }
            val repository = NetworkSkeletalDataRepository(remote, cache)

            val briefing = repository.loadBriefing()

            assertEquals(ContentOrigin.CACHED_BACKEND, briefing.disclosure.origin)
            assertTrue(briefing.disclosure.message.contains("live refresh failed"))
            assertEquals(listOf("paper-1"), briefing.papers.map { it.id })
            assertEquals("Cached reason", briefing.papers.single().summary)
        }

    @Test
    fun paperAcceptedThenSucceeded_returnsSourceMatchedLiveSummary() =
        runBlocking {
            val remote = FakeRemote()
            val cache = FakeCache()
            remote.paper = paper("paper-1", "First paper")
            remote.summaryResults.add(
                RemoteResource.Accepted(
                    JobDto(
                        id = "job-1",
                        stage = "summarize_paper",
                        status = "running",
                    ),
                ),
            )
            remote.summaryResults.add(
                RemoteResource.Ready(
                    SummaryDto(
                        paperId = "paper-1",
                        status = "ready",
                        tldr = "A live generated summary.",
                        keyClaims = listOf("A grounded claim"),
                        methodology = "A measured method",
                        limitations = "A stated limitation",
                        sourceMatchStatus = "matched",
                    ),
                ),
            )
            remote.job = JobDto(id = "job-1", stage = "summarize_paper", status = "succeeded")
            val repository = NetworkSkeletalDataRepository(remote, cache) { REFRESHED_AT }

            val accepted = repository.loadPaper("paper-1") as PaperContentResult.Processing
            val ready = repository.refreshPaper("paper-1", accepted.jobId) as PaperContentResult.Ready

            assertEquals("A live generated summary.", ready.paper.paper.summary)
            assertEquals(SourceMatchUiStatus.MATCHED, ready.paper.sourceMatchStatus)
            assertEquals(ContentOrigin.LIVE_BACKEND, ready.paper.disclosure.origin)
            assertEquals(listOf("paper-1", "paper-1"), cache.openedPaperIds)
        }

    @Test
    fun paperFailure_usesCachedMetadataWithoutClaimingGeneratedSummary() =
        runBlocking {
            val remote = FakeRemote().apply { paperFailure = IOException("offline") }
            val cachedPaper = cachedPaper("paper-1", "Cached paper")
            val cache = FakeCache().apply { papers[cachedPaper.id] = cachedPaper }
            val repository = NetworkSkeletalDataRepository(remote, cache)

            val ready = repository.loadPaper("paper-1") as PaperContentResult.Ready

            assertEquals(ContentOrigin.CACHED_BACKEND, ready.paper.disclosure.origin)
            assertEquals(SourceMatchUiStatus.NOT_CHECKED, ready.paper.sourceMatchStatus)
            assertTrue(ready.paper.keyClaims.isEmpty())
            assertTrue(
                ready.paper.disclosure.message
                    .contains("does not include a generated summary"),
            )
        }

    @Test
    fun insufficientEvidenceAnswer_hasNoInventedCitation() =
        runBlocking {
            val remote = FakeRemote()
            val cachedPaper = cachedPaper("paper-1", "Cached paper")
            val cache = FakeCache().apply { papers[cachedPaper.id] = cachedPaper }
            remote.answer =
                AnswerDto(
                    answer = "There is not enough evidence in the indexed paper.",
                    citations = emptyList(),
                    sourceMatchStatus = "insufficient_evidence",
                    conversationId = "conversation-1",
                )
            val repository = NetworkSkeletalDataRepository(remote, cache)
            val question = "Which finding is not supported by the indexed evidence?"

            val qa = repository.askQuestion("paper-1", question)

            assertEquals(SourceMatchUiStatus.INSUFFICIENT_EVIDENCE, qa.sourceMatchStatus)
            assertTrue(qa.sources.isEmpty())
            assertEquals(ContentOrigin.LIVE_BACKEND, qa.disclosure.origin)
            assertEquals(question, qa.question)
            assertEquals(qa.question, remote.questions.single().question)
            assertEquals("paper-1", remote.questions.single().paperId)
        }

    @Test
    fun unmatchedCitation_isShownWithoutClaimingItMatched() =
        runBlocking {
            val remote = FakeRemote()
            val cachedPaper = cachedPaper("paper-1", "Cached paper")
            val cache = FakeCache().apply { papers[cachedPaper.id] = cachedPaper }
            remote.answer =
                AnswerDto(
                    answer = "A partially supported answer.",
                    citations =
                        listOf(
                            CitationDto(
                                paperId = "paper-1",
                                arxivId = "2607.00001",
                                sectionTitle = "Evaluation",
                                sourceMatch = false,
                            ),
                        ),
                    sourceMatchStatus = "partial",
                    conversationId = "conversation-1",
                )
            val repository = NetworkSkeletalDataRepository(remote, cache)
            val question = "How was the evaluation conducted?"

            val qa = repository.askQuestion("paper-1", question)

            assertEquals(SourceMatchUiStatus.PARTIAL, qa.sourceMatchStatus)
            assertEquals(SourceMatchUiStatus.UNMATCHED, qa.sources.single().matchStatus)
        }

    @Test
    fun invalidQuestion_isRejectedBeforeCallingBackend() {
        val remote = FakeRemote()
        val repository = NetworkSkeletalDataRepository(remote, FakeCache())

        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { repository.askQuestion("paper-1", "   ") }
        }
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { repository.askQuestion("paper-1", "A".repeat(QUESTION_MAX_LENGTH + 1)) }
        }
        assertTrue(remote.questions.isEmpty())
    }

    private class FakeRemote : MnemeRemoteDataSource {
        var preferences: PreferencesDto = preferences()
        var digestResult: RemoteResource<DigestDto> = RemoteResource.Ready(digest())
        var paper: PaperDto = paper("paper-1", "Paper")
        var job: JobDto = JobDto(id = "job-1", stage = "summarize_paper", status = "running")
        var answer: AnswerDto =
            AnswerDto(
                answer = "Answer",
                citations = emptyList(),
                sourceMatchStatus = "insufficient_evidence",
                conversationId = "conversation-1",
            )
        var briefingFailure: Exception? = null
        var paperFailure: Exception? = null
        val summaryResults = ArrayDeque<RemoteResource<SummaryDto>>()
        val questions = mutableListOf<QuestionDto>()

        override suspend fun getHealth(): HealthDto = HealthDto("ok")

        override suspend fun listPapers(limit: Int): PaperPageDto = PaperPageDto(listOf(paper))

        override suspend fun getPaper(paperId: String): PaperDto {
            paperFailure?.let { throw it }
            return paper
        }

        override suspend fun getPaperSummary(paperId: String): RemoteResource<SummaryDto> = summaryResults.removeFirst()

        override suspend fun getPreferences(): PreferencesDto {
            briefingFailure?.let { throw it }
            return preferences
        }

        override suspend fun updatePreferences(update: PreferenceUpdateDto): PreferencesDto = preferences

        override suspend fun listDigests(limit: Int): DigestPageDto = DigestPageDto(emptyList())

        override suspend fun generateRecommendedDigest(): RemoteResource<DigestDto> {
            briefingFailure?.let { throw it }
            return digestResult
        }

        override suspend fun getJob(jobId: String): JobDto = job

        override suspend fun askQuestion(question: QuestionDto): AnswerDto {
            questions += question
            return answer
        }
    }

    private class FakeCache : SkeletalCache {
        var cachedBriefing: CachedBriefing? = null
        var storedDigest: DigestDto? = null
        var storedBriefingAt: Long? = null
        val papers = mutableMapOf<String, CachedPaper>()
        val openedPaperIds = mutableListOf<String>()

        override suspend fun storeBriefing(
            preferences: PreferencesDto,
            digest: DigestDto,
            refreshedAtEpochMillis: Long,
        ) {
            storedDigest = digest
            storedBriefingAt = refreshedAtEpochMillis
        }

        override suspend fun getBriefing(): CachedBriefing? = cachedBriefing

        override suspend fun storePaper(
            paper: PaperDto,
            refreshedAtEpochMillis: Long,
        ) {
            papers[paper.id] =
                CachedPaper(
                    id = paper.id,
                    arxivId = paper.arxivId,
                    title = paper.title,
                    authors = paper.authors,
                    abstractText = paper.abstract,
                    primaryCategory = paper.primaryCategory,
                    pdfUrl = paper.pdfUrl,
                    processingStatus = paper.processingStatus,
                    updatedAtEpochMillis = refreshedAtEpochMillis,
                )
        }

        override suspend fun getPaper(paperId: String): CachedPaper? = papers[paperId]

        override suspend fun markPaperOpened(
            paperId: String,
            openedAtEpochMillis: Long,
        ) {
            openedPaperIds += paperId
        }
    }

    companion object {
        private const val REFRESHED_AT = 1_721_632_800_000L

        private fun preferences(): PreferencesDto =
            PreferencesDto(
                topics = listOf("retrieval", "mobile systems"),
                followedAuthors = emptyList(),
                modelVersion = 2,
                updatedAt = "2026-07-22T08:00:00Z",
            )

        private fun paper(
            id: String,
            title: String,
        ): PaperDto =
            PaperDto(
                id = id,
                arxivId = "2607.00001",
                title = title,
                authors = listOf("A. Researcher"),
                abstract = "A source abstract for $title.",
                primaryCategory = "cs.IR",
                categories = listOf("cs.IR"),
                pdfUrl = "https://arxiv.org/pdf/2607.00001",
                processingStatus = "ready",
                publishedAt = "2026-07-21T08:00:00Z",
                updatedAt = "2026-07-22T08:00:00Z",
            )

        private fun entry(
            paper: PaperDto,
            rank: Int,
            reason: String,
        ): DigestEntryDto =
            DigestEntryDto(
                paper = paper,
                rank = rank,
                relevanceScore = 0.8,
                recommendationReason = reason,
            )

        private fun digest(entries: List<DigestEntryDto> = emptyList()): DigestDto =
            DigestDto(
                id = "digest-1",
                digestType = "manual",
                generatedAt = "2026-07-22T08:00:00Z",
                entries = entries,
            )

        private fun cachedPaper(
            id: String,
            title: String,
        ): CachedPaper =
            CachedPaper(
                id = id,
                arxivId = "2607.00001",
                title = title,
                authors = listOf("A. Researcher"),
                abstractText = "A cached abstract.",
                primaryCategory = "cs.IR",
                pdfUrl = "https://arxiv.org/pdf/2607.00001",
                processingStatus = "ready",
                updatedAtEpochMillis = REFRESHED_AT,
            )

        private fun cachedBriefing(): CachedBriefing =
            CachedBriefing(
                digest =
                    DigestEntity(
                        id = "digest-1",
                        title = "Cached research briefing",
                        summary = "cache-payload",
                        digestType = "manual",
                        generatedAtEpochMillis = REFRESHED_AT,
                        lastSyncedAtEpochMillis = REFRESHED_AT,
                    ),
                description = "One cached paper.",
                interests = listOf("retrieval"),
                papers = listOf(cachedPaper("paper-1", "Cached paper")),
                recommendationReasons = mapOf("paper-1" to "Cached reason"),
                refreshedAtEpochMillis = REFRESHED_AT,
            )
    }
}
