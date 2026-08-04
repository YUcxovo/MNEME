package com.mneme.app.data.network

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class MnemeApiClientTest {
    private lateinit var server: MockWebServer

    @Before
    fun startServer() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun stopServer() {
        server.shutdown()
    }

    @Test
    fun healthRequest_usesVersionedPathWithoutBearerToken() =
        runBlocking {
            server.enqueue(jsonResponse("""{"status":"ok"}"""))
            val remote = createRemote()

            assertEquals("ok", remote.getHealth().status)

            val request = server.takeRequest()
            assertEquals("/v1/health", request.path)
            assertNull(request.getHeader("Authorization"))
        }

    @Test
    fun protectedRequest_addsBearerAndDecodesSnakeCaseContract() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "topics": ["retrieval", "agents"],
                      "followed_authors": ["Ada Lovelace"],
                      "model_version": 4,
                      "updated_at": "2026-07-22T08:00:00Z"
                    }
                    """.trimIndent(),
                ),
            )
            val remote = createRemote()

            val preferences = remote.getPreferences()

            assertEquals(listOf("retrieval", "agents"), preferences.topics)
            assertEquals(listOf("Ada Lovelace"), preferences.followedAuthors)
            assertEquals(4, preferences.modelVersion)
            val request = server.takeRequest()
            assertEquals("/v1/users/me/preferences", request.path)
            assertEquals("Bearer local-test-token", request.getHeader("Authorization"))
        }

    @Test
    fun summaryAccepted_decodesDurableJobWithoutTreatingItAsSummary() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "id": "99999999-9999-4999-8999-999999999999",
                      "stage": "summarize_paper",
                      "status": "running",
                      "updated_at": "2026-07-22T08:00:00Z"
                    }
                    """.trimIndent(),
                    statusCode = 202,
                ),
            )

            val result = createRemote().getPaperSummary(PAPER_ID)

            assertTrue(result is RemoteResource.Accepted)
            assertEquals("summarize_paper", (result as RemoteResource.Accepted).job.stage)
            assertEquals("/v1/papers/$PAPER_ID/summary", server.takeRequest().path)
        }

    @Test
    fun summaryReady_decodesMatchedAndUnmatchedClaimSources() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "paper_id": "$PAPER_ID",
                      "status": "ready",
                      "tldr": "A source-linked summary.",
                      "key_claims": ["Matched claim", "Unmatched claim"],
                      "source_match_status": "partial",
                      "claims": [
                        {
                          "text": "Matched claim",
                          "matched": true,
                          "source": {
                            "chunk_id": "33333333-3333-4333-8333-333333333333",
                            "chunk_index": 4,
                            "section_title": "Evaluation",
                            "page_start": 7,
                            "page_end": 8,
                            "excerpt": "A synthetic evaluation excerpt."
                          }
                        },
                        {
                          "text": "Unmatched claim",
                          "matched": false,
                          "source": null
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
            )

            val result = createRemote().getPaperSummary(PAPER_ID) as RemoteResource.Ready
            val summary = result.value

            assertEquals(listOf("Matched claim", "Unmatched claim"), summary.keyClaims)
            assertEquals(2, summary.claims.size)
            assertTrue(summary.claims.first().matched)
            assertEquals(
                "Evaluation",
                summary.claims
                    .first()
                    .source
                    ?.sectionTitle,
            )
            assertEquals(
                7,
                summary.claims
                    .first()
                    .source
                    ?.pageStart,
            )
            assertEquals(null, summary.claims.last().source)
        }

    @Test
    fun legacySummaryReady_defaultsToNoPerClaimSources() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "paper_id": "$PAPER_ID",
                      "status": "ready",
                      "tldr": "A legacy summary.",
                      "key_claims": ["Legacy claim"],
                      "source_match_status": "not_checked"
                    }
                    """.trimIndent(),
                ),
            )

            val result = createRemote().getPaperSummary(PAPER_ID) as RemoteResource.Ready

            assertTrue(result.value.claims.isEmpty())
        }

    @Test
    fun seedInitialization_serializesReferenceAndDecodesCompletedBriefing() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "seed_arxiv_id": "2607.00001",
                      "category": "cs.IR",
                      "paper_count": 0,
                      "preferences": {
                        "topics": ["cs.IR"],
                        "followed_authors": [],
                        "model_version": 2
                      },
                      "digest": {
                        "id": "77777777-7777-4777-8777-777777777777",
                        "digest_type": "manual",
                        "generated_at": "2026-07-22T08:00:00Z",
                        "entries": []
                      }
                    }
                    """.trimIndent(),
                ),
            )

            val result =
                createRemote().initializeFromSeed(
                    SeedInitializationRequestDto("https://arxiv.org/abs/2607.00001"),
                )

            assertEquals("2607.00001", result.seedArxivId)
            assertEquals(listOf("cs.IR"), result.preferences.topics)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/v1/onboarding/seed", request.path)
            assertTrue(request.body.readUtf8().contains("https://arxiv.org/abs/2607.00001"))
        }

    @Test
    fun apiError_preservesStablePublicErrorFields() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "code": "invalid_token",
                      "message": "The demo token is invalid.",
                      "request_id": "request-123"
                    }
                    """.trimIndent(),
                    statusCode = 401,
                ),
            )

            val error =
                runCatching { createRemote().getPreferences() }
                    .exceptionOrNull() as MnemeApiException

            assertEquals(401, error.statusCode)
            assertEquals("invalid_token", error.errorCode)
            assertEquals("The demo token is invalid.", error.message)
            assertEquals("request-123", error.requestId)
        }

    @Test
    fun askQuestion_serializesFrozenQuestionShape() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "answer": "The paper introduces a retrieval method.",
                      "citations": [],
                      "source_match_status": "insufficient_evidence",
                      "conversation_id": "88888888-8888-4888-8888-888888888888"
                    }
                    """.trimIndent(),
                ),
            )

            createRemote().askQuestion(
                QuestionDto(
                    question = "What is the main contribution?",
                    paperId = PAPER_ID,
                ),
            )

            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/v1/qa/ask", request.path)
            val body = request.body.readUtf8()
            assertTrue(body.contains("\"paper_id\":\"$PAPER_ID\""))
            assertTrue(body.contains("\"question\":\"What is the main contribution?\""))
        }

    @Test
    fun askFollowUpQuestion_serializesConversationIdentity() =
        runBlocking {
            val conversationId = "88888888-8888-4888-8888-888888888888"
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "answer": "The follow-up stays in the same conversation.",
                      "citations": [],
                      "source_match_status": "insufficient_evidence",
                      "conversation_id": "$conversationId"
                    }
                    """.trimIndent(),
                ),
            )

            createRemote().askQuestion(
                QuestionDto(
                    question = "How does that mechanism work?",
                    paperId = PAPER_ID,
                    conversationId = conversationId,
                ),
            )

            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/v1/qa/ask", request.path)
            assertTrue(request.body.readUtf8().contains("\"conversation_id\":\"$conversationId\""))
        }

    @Test
    fun citationGraph_decodesFrozenShapeAndSendsBounds() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "center_id": "$PAPER_ID",
                      "nodes": [
                        {
                          "id": "$PAPER_ID",
                          "title": "Center paper",
                          "category": "cs.IR",
                          "cluster_id": "cluster-1",
                          "rank_score": 1.0
                        },
                        {
                          "id": "$CITED_PAPER_ID",
                          "title": "Cited paper"
                        }
                      ],
                      "edges": [
                        {
                          "source": "$PAPER_ID",
                          "target": "$CITED_PAPER_ID",
                          "weight": 0.75
                        }
                      ],
                      "algorithm_status": "ready",
                      "graph_version": "citation-graph-v1"
                    }
                    """.trimIndent(),
                ),
            )

            val graph = createRemote().getPaperGraph(PAPER_ID, depth = 2, limit = 50)

            assertEquals(PAPER_ID, graph.centerId)
            assertEquals("cluster-1", graph.nodes.first().clusterId)
            assertEquals(CITED_PAPER_ID, graph.edges.single().target)
            assertEquals("ready", graph.algorithmStatus)
            val request = server.takeRequest()
            assertEquals("/v1/graph/$PAPER_ID?depth=2&limit=50", request.path)
            assertEquals("Bearer local-test-token", request.getHeader("Authorization"))
        }

    @Test
    fun uploadEvents_serializesFrozenBatchAndDecodesIdempotentCounts() =
        runBlocking {
            server.enqueue(
                jsonResponse(
                    """
                    {
                      "accepted": 1,
                      "duplicates": 1
                    }
                    """.trimIndent(),
                ),
            )
            val firstEventId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            val secondEventId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

            val result =
                createRemote().uploadEvents(
                    listOf(
                        UserEventDto(
                            eventId = firstEventId,
                            eventType = "paper_opened",
                            paperId = PAPER_ID,
                            occurredAt = "2026-07-24T03:00:00Z",
                            durationMillis = 45_000,
                        ),
                        UserEventDto(
                            eventId = secondEventId,
                            eventType = "question_asked",
                            paperId = PAPER_ID,
                            occurredAt = "2026-07-24T03:01:00Z",
                        ),
                    ),
                )

            assertEquals(1, result.accepted)
            assertEquals(1, result.duplicates)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/v1/events", request.path)
            assertEquals("Bearer local-test-token", request.getHeader("Authorization"))
            val body = request.body.readUtf8()
            assertTrue(body.startsWith("["))
            assertTrue(body.contains("\"event_id\":\"$firstEventId\""))
            assertTrue(body.contains("\"event_type\":\"paper_opened\""))
            assertTrue(body.contains("\"paper_id\":\"$PAPER_ID\""))
            assertTrue(body.contains("\"occurred_at\":\"2026-07-24T03:00:00Z\""))
            assertTrue(body.contains("\"duration_ms\":45000"))
            assertTrue(body.contains("\"event_id\":\"$secondEventId\""))
        }

    @Test
    fun baseUrl_requiresFrozenVersionPrefix() {
        val error =
            runCatching { MnemeApiClient.normalizeBaseUrl("http://localhost:8000/") }
                .exceptionOrNull()

        assertTrue(error is IllegalArgumentException)
        assertEquals(
            "http://localhost:8000/v1/",
            MnemeApiClient.normalizeBaseUrl("http://localhost:8000/v1"),
        )
    }

    private fun createRemote(): MnemeRemoteDataSource =
        MnemeApiClient.create(
            baseUrl = server.url("/v1/").toString(),
            demoToken = "local-test-token",
        )

    private fun jsonResponse(
        body: String,
        statusCode: Int = 200,
    ): MockResponse =
        MockResponse()
            .setResponseCode(statusCode)
            .setHeader("Content-Type", "application/json")
            .setBody(body)

    companion object {
        private const val PAPER_ID = "11111111-1111-4111-8111-111111111111"
        private const val CITED_PAPER_ID = "22222222-2222-4222-8222-222222222222"
    }
}
