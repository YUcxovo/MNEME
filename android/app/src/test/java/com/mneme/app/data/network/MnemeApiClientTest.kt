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
    fun eventUpload_serializesFrozenBatchAndDecodesIdempotencyResult() =
        runBlocking {
            server.enqueue(jsonResponse("""{"accepted":1,"duplicates":0}"""))

            val result =
                createRemote().ingestEvents(
                    listOf(
                        UserEventDto(
                            eventId = "22222222-2222-4222-8222-222222222222",
                            eventType = "paper_opened",
                            paperId = PAPER_ID,
                            occurredAt = "2026-07-24T10:00:00Z",
                            durationMillis = 4000,
                        ),
                    ),
                )

            assertEquals(1, result.accepted)
            assertEquals(0, result.duplicates)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/v1/events", request.path)
            val body = request.body.readUtf8()
            assertTrue(body.contains("\"event_type\":\"paper_opened\""))
            assertTrue(body.contains("\"occurred_at\":\"2026-07-24T10:00:00Z\""))
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
    }
}
