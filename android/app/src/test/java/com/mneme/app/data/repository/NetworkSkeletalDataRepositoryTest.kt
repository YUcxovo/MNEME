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
import com.mneme.app.data.network.EventIngestionResultDto
import com.mneme.app.data.network.GraphDto
import com.mneme.app.data.network.GraphEdgeDto
import com.mneme.app.data.network.GraphNodeDto
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
import com.mneme.app.data.network.SeedInitializationDto
import com.mneme.app.data.network.SeedInitializationRequestDto
import com.mneme.app.data.network.SummaryDto
import com.mneme.app.data.network.UserEventDto
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphAlgorithmUiStatus
import com.mneme.app.ui.model.SourceMatchUiStatus
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.SerializationException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class NetworkSkeletalDataRepositoryTest {
    @Test
    fun restoreBriefing_withoutDeviceCache_requiresSeedOnboarding() =
        runBlocking {
            val repository = NetworkSkeletalDataRepository(FakeRemote(), FakeCache())

            assertEquals(null, repository.restoreBriefing())
        }

    @Test
    fun restoreBriefing_withDeviceCache_returnsPreviousBriefing() =
        runBlocking {
            val cache = FakeCache().apply { cachedBriefing = cachedBriefing() }
            val repository = NetworkSkeletalDataRepository(FakeRemote(), cache)

            val restored = checkNotNull(repository.restoreBriefing())

            assertEquals(ContentOrigin.CACHED_BACKEND, restored.disclosure.origin)
            assertTrue(restored.disclosure.message.contains("this device"))
            assertEquals(listOf("paper-1"), restored.papers.map { it.id })
            assertEquals("Cached reason", restored.papers.single().summary)
        }

    @Test
    fun initializeFromSeed_waitsForCompletedBackendBriefingAndCachesIt() =
        runBlocking {
            val remote = FakeRemote()
            val cache = FakeCache()
            val repository = NetworkSkeletalDataRepository(remote, cache) { REFRESHED_AT }

            val briefing = repository.initializeFromSeed(" https://arxiv.org/abs/2607.00001 ")

            assertEquals("https://arxiv.org/abs/2607.00001", remote.seedRequests.single().arxivReference)
            assertEquals(listOf("cs.IR"), briefing.interests)
            assertEquals(listOf("paper-1"), briefing.papers.map { it.id })
            assertEquals(ContentOrigin.LIVE_BACKEND, briefing.disclosure.origin)
            assertEquals(REFRESHED_AT, cache.storedBriefingAt)
        }

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
    fun updateInterests_preservesAuthorsCachesCanonicalTopicsAndFeedsNextBriefing() =
        runBlocking {
            val remote =
                FakeRemote().apply {
                    preferences =
                        preferences().copy(
                            followedAuthors = listOf("ada lovelace"),
                        )
                }
            val cache = FakeCache()
            val repository = NetworkSkeletalDataRepository(remote, cache) { REFRESHED_AT }

            val briefing =
                repository.updateInterests(
                    listOf("  Programming Languages  ", "programming languages", "Software Engineering"),
                )
            val topics = briefing.interests

            assertEquals(
                listOf("Programming Languages", "Software Engineering"),
                remote.preferenceUpdates.single().topics,
            )
            assertEquals(
                listOf("ada lovelace"),
                remote.preferenceUpdates.single().followedAuthors,
            )
            assertEquals(
                listOf("Programming Languages", "Software Engineering"),
                topics,
            )
            assertEquals(topics, cache.storedPreferences?.topics)
            assertEquals(topics, briefing.interests)
            assertEquals(
                listOf("get_preferences", "update_preferences"),
                remote.operations.take(2),
            )
            assertTrue(
                remote.operations.indexOf("update_preferences") <
                    remote.operations.indexOf("generate_digest"),
            )
        }

    @Test
    fun updateInterests_pendingDigestDoesNotChangeDeviceCache() {
        val remote =
            FakeRemote().apply {
                digestResult =
                    RemoteResource.Accepted(
                        JobDto(
                            id = "preparing-updated-digest",
                            stage = "generate_digest",
                            status = "running",
                        ),
                    )
            }
        val cache = FakeCache()
        val repository = NetworkSkeletalDataRepository(remote, cache)

        assertThrows(ContentPendingException::class.java) {
            runBlocking { repository.updateInterests(listOf("systems")) }
        }

        assertEquals(listOf("systems"), remote.preferenceUpdates.single().topics)
        assertEquals(null, cache.storedPreferences)
        assertEquals(null, cache.storedDigest)
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
    fun mismatchedPaperResponse_usesOnlyTheRequestedCachedPaper() =
        runBlocking {
            val remote = FakeRemote().apply { paper = paper("paper-2", "Wrong paper") }
            val requestedPaper = cachedPaper("paper-1", "Requested cached paper")
            val cache = FakeCache().apply { papers[requestedPaper.id] = requestedPaper }
            val repository = NetworkSkeletalDataRepository(remote, cache)

            val ready = repository.loadPaper("paper-1") as PaperContentResult.Ready

            assertEquals("paper-1", ready.paper.paper.id)
            assertEquals("Requested cached paper", ready.paper.paper.title)
            assertEquals(ContentOrigin.CACHED_BACKEND, ready.paper.disclosure.origin)
            assertTrue("paper-2" !in cache.papers)
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
            assertEquals("conversation-1", qa.conversationId)
            assertEquals(qa.question, remote.questions.single().question)
            assertEquals("paper-1", remote.questions.single().paperId)
        }

    @Test
    fun followUpQuestion_reusesReturnedConversationIdentity() =
        runBlocking {
            val remote = FakeRemote()
            val cachedPaper = cachedPaper("paper-1", "Cached paper")
            val cache = FakeCache().apply { papers[cachedPaper.id] = cachedPaper }
            val repository = NetworkSkeletalDataRepository(remote, cache)

            val first = repository.askQuestion("paper-1", "What is the main result?")
            val second =
                repository.askQuestion(
                    paperId = "paper-1",
                    question = "Which evidence supports it?",
                    conversationId = first.conversationId,
                )

            assertEquals("conversation-1", second.conversationId)
            assertEquals(null, remote.questions[0].conversationId)
            assertEquals("conversation-1", remote.questions[1].conversationId)
        }

    @Test
    fun changedConversationIdentity_isRejectedAsContractMismatch() {
        val remote = FakeRemote()
        val cachedPaper = cachedPaper("paper-1", "Cached paper")
        val cache = FakeCache().apply { papers[cachedPaper.id] = cachedPaper }
        val repository = NetworkSkeletalDataRepository(remote, cache)

        assertThrows(SerializationException::class.java) {
            runBlocking {
                repository.askQuestion(
                    paperId = "paper-1",
                    question = "Continue the explanation.",
                    conversationId = "different-conversation",
                )
            }
        }
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

    @Test
    fun loadGraph_mapsFrozenDirectionAndRequestsBoundedDepthTwoView() =
        runBlocking {
            val remote = FakeRemote()
            remote.graph =
                graph(
                    status = "ready",
                    edges = listOf(GraphEdgeDto(source = "paper-1", target = "paper-2", weight = 0.8)),
                )
            val repository = NetworkSkeletalDataRepository(remote, FakeCache())

            val graph = repository.loadGraph("paper-1")

            assertEquals("paper-1", graph.centerId)
            assertEquals(GraphAlgorithmUiStatus.READY, graph.algorithmStatus)
            assertEquals("citation-graph-v1", graph.graphVersion)
            assertEquals("paper-1", graph.edges.single().source)
            assertEquals("paper-2", graph.edges.single().target)
            assertEquals(ContentOrigin.LIVE_BACKEND, graph.disclosure.origin)
            assertEquals(Triple("paper-1", 2, 50), remote.graphRequests.single())
        }

    @Test
    fun fallbackGraph_isDisclosedAsBackendBaseline() =
        runBlocking {
            val remote = FakeRemote().apply { graph = graph(status = "fallback") }
            val repository = NetworkSkeletalDataRepository(remote, FakeCache())

            val graph = repository.loadGraph("paper-1")

            assertEquals(GraphAlgorithmUiStatus.FALLBACK, graph.algorithmStatus)
            assertTrue(graph.disclosure.message.contains("deterministic baseline"))
        }

    @Test
    fun graphOutsideNodeBoundary_isRejectedAsContractMismatch() {
        val remote =
            FakeRemote().apply {
                graph =
                    graph(
                        status = "ready",
                        edges = listOf(GraphEdgeDto(source = "paper-1", target = "missing")),
                    )
            }
        val repository = NetworkSkeletalDataRepository(remote, FakeCache())

        assertThrows(SerializationException::class.java) {
            runBlocking { repository.loadGraph("paper-1") }
        }
    }

    @Test
    fun graphWithUnknownAlgorithmStatus_isRejectedAsContractMismatch() {
        val remote = FakeRemote().apply { graph = graph(status = "experimental") }
        val repository = NetworkSkeletalDataRepository(remote, FakeCache())

        assertThrows(SerializationException::class.java) {
            runBlocking { repository.loadGraph("paper-1") }
        }
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
        var graph: GraphDto = graph(status = "fallback")
        var briefingFailure: Exception? = null
        var paperFailure: Exception? = null
        val summaryResults = ArrayDeque<RemoteResource<SummaryDto>>()
        val questions = mutableListOf<QuestionDto>()
        val seedRequests = mutableListOf<SeedInitializationRequestDto>()
        val graphRequests = mutableListOf<Triple<String, Int, Int>>()
        val preferenceUpdates = mutableListOf<PreferenceUpdateDto>()
        val operations = mutableListOf<String>()

        override suspend fun getHealth(): HealthDto = HealthDto("ok")

        override suspend fun listPapers(limit: Int): PaperPageDto = PaperPageDto(listOf(paper))

        override suspend fun getPaper(paperId: String): PaperDto {
            paperFailure?.let { throw it }
            return paper
        }

        override suspend fun getPaperSummary(paperId: String): RemoteResource<SummaryDto> = summaryResults.removeFirst()

        override suspend fun getPreferences(): PreferencesDto {
            operations += "get_preferences"
            briefingFailure?.let { throw it }
            return preferences
        }

        override suspend fun updatePreferences(update: PreferenceUpdateDto): PreferencesDto {
            operations += "update_preferences"
            preferenceUpdates += update
            preferences =
                preferences.copy(
                    topics = update.topics,
                    followedAuthors = update.followedAuthors,
                )
            return preferences
        }

        override suspend fun initializeFromSeed(request: SeedInitializationRequestDto): SeedInitializationDto {
            seedRequests += request
            val seedPreferences = preferences().copy(topics = listOf("cs.IR"))
            return SeedInitializationDto(
                seedArxivId = "2607.00001",
                category = "cs.IR",
                paperCount = 1,
                preferences = seedPreferences,
                digest = digest(entries = listOf(entry(paper, rank = 1, reason = "Related"))),
            )
        }

        override suspend fun listDigests(limit: Int): DigestPageDto = DigestPageDto(emptyList())

        override suspend fun generateRecommendedDigest(): RemoteResource<DigestDto> {
            operations += "generate_digest"
            briefingFailure?.let { throw it }
            return digestResult
        }

        override suspend fun getJob(jobId: String): JobDto = job

        override suspend fun askQuestion(question: QuestionDto): AnswerDto {
            questions += question
            return answer
        }

        override suspend fun getPaperGraph(
            paperId: String,
            depth: Int,
            limit: Int,
        ): GraphDto {
            graphRequests += Triple(paperId, depth, limit)
            return graph
        }

        override suspend fun uploadEvents(events: List<UserEventDto>): EventIngestionResultDto =
            EventIngestionResultDto(accepted = events.size, duplicates = 0)
    }

    private class FakeCache : SkeletalCache {
        var cachedBriefing: CachedBriefing? = null
        var storedDigest: DigestDto? = null
        var storedPreferences: PreferencesDto? = null
        var storedBriefingAt: Long? = null
        val papers = mutableMapOf<String, CachedPaper>()
        val openedPaperIds = mutableListOf<String>()

        override suspend fun storeBriefing(
            preferences: PreferencesDto,
            digest: DigestDto,
            refreshedAtEpochMillis: Long,
        ) {
            storedDigest = digest
            storedPreferences = preferences
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

        private fun graph(
            status: String,
            edges: List<GraphEdgeDto> = emptyList(),
        ): GraphDto =
            GraphDto(
                centerId = "paper-1",
                nodes =
                    listOf(
                        GraphNodeDto(
                            id = "paper-1",
                            title = "Center paper",
                            category = "cs.IR",
                            clusterId = "cluster-1",
                            rankScore = 1.0,
                        ),
                        GraphNodeDto(
                            id = "paper-2",
                            title = "Cited paper",
                            category = "cs.LG",
                            clusterId = "cluster-2",
                            rankScore = 0.6,
                        ),
                    ),
                edges = edges,
                algorithmStatus = status,
                graphVersion = "citation-graph-v1",
            )
    }
}
