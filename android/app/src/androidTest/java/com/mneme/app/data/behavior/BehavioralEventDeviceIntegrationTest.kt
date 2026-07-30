@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.data.behavior

import android.content.Context
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.entity.BehavioralEventSyncState
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.ui.MnemeApp
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.theme.MnemeTheme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.ArrayDeque
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

@RunWith(AndroidJUnit4::class)
class BehavioralEventDeviceIntegrationTest {
    @get:Rule
    val composeRule = createComposeRule()

    private lateinit var database: MnemeDatabase
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database =
            Room
                .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
                .allowMainThreadQueries()
                .build()
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
        database.close()
    }

    @Test
    fun visibleActions_crossRoomRetrofitAndHttpBoundaries() {
        val eventIds =
            ArrayDeque(
                listOf(
                    UUID.fromString("8f0a1d3b-cc41-43f0-97c2-c175341ef07c"),
                    UUID.fromString("e63ff7fe-4f7c-45eb-a188-df825de81f4f"),
                    UUID.fromString("9e8e9965-936d-462f-90b4-f39b4d44aa2f"),
                    UUID.fromString("8719343c-7cbb-4277-a727-bc2c9d619a84"),
                    UUID.fromString("e29530b6-76d1-45bb-a48f-e46fd85c37f4"),
                ),
            )
        val store =
            BehavioralEventRepository(
                behavioralEventDao = database.behavioralEventDao(),
                idGenerator = eventIds::removeFirst,
            )
        val scheduled = AtomicInteger()
        val tracker =
            QueuedBehavioralEventTracker(
                store = store,
                scheduleSync = { scheduled.incrementAndGet() },
                nowEpochMillis = { EVENT_TRACE_TIME },
            )
        val viewModel = MnemeViewModel(EventTraceRepository(), tracker)
        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    onOpenSource = {},
                    onSharePaper = { _, _ -> },
                )
            }
        }

        waitForEventCount(store, 1)
        composeRule.onNodeWithText(EVENT_TRACE_PAPER_TITLE).performClick()
        waitForEventCount(store, 2)
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("save-paper-action"),
        )
        composeRule.onNodeWithTag("save-paper-action").performClick()
        waitForEventCount(store, 3)
        composeRule.onNodeWithTag("share-paper-action").performClick()
        waitForEventCount(store, 4)
        composeRule.onNodeWithTag("paper-detail-screen").performScrollToNode(
            hasTestTag("ask-question-action"),
        )
        composeRule.onNodeWithTag("ask-question-action").performClick()
        composeRule.onNodeWithTag("qa-question-input").performTextInput(EVENT_TRACE_QUESTION)
        composeRule.onNodeWithTag("qa-submit-question").performClick()
        waitForEventCount(store, 5)

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"accepted":4,"duplicates":1}"""),
        )
        val remote =
            MnemeApiClient.create(
                baseUrl = server.url("/v1/").toString(),
                demoToken = "e4-device-token",
            )
        val coordinator =
            BehavioralEventSyncCoordinator(
                store = store,
                remote = remote,
                nowEpochMillis = { EVENT_TRACE_TIME + 1_000 },
            )

        val result = runBlocking { coordinator.syncPending() }

        assertEquals(
            BehavioralEventSyncResult.Synced(
                processed = 5,
                accepted = 4,
                duplicates = 1,
            ),
            result,
        )
        val request = server.takeRequest()
        assertEquals("/v1/events", request.path)
        assertEquals("Bearer e4-device-token", request.getHeader("Authorization"))
        val payload =
            MnemeApiClient.json
                .parseToJsonElement(request.body.readUtf8())
                .jsonArray
        assertEquals(5, payload.size)
        assertEquals(
            setOf(
                "paper_impression",
                "paper_opened",
                "paper_saved",
                "paper_shared",
                "question_asked",
            ),
            payload
                .map {
                    it.jsonObject
                        .getValue("event_type")
                        .jsonPrimitive.content
                }.toSet(),
        )
        assertEquals(
            setOf(
                "8f0a1d3b-cc41-43f0-97c2-c175341ef07c",
                "e63ff7fe-4f7c-45eb-a188-df825de81f4f",
                "9e8e9965-936d-462f-90b4-f39b4d44aa2f",
                "8719343c-7cbb-4277-a727-bc2c9d619a84",
                "e29530b6-76d1-45bb-a48f-e46fd85c37f4",
            ),
            payload
                .map {
                    it.jsonObject
                        .getValue("event_id")
                        .jsonPrimitive.content
                }.toSet(),
        )
        assertTrue(
            payload.all {
                it.jsonObject
                    .getValue("paper_id")
                    .jsonPrimitive.content == EVENT_TRACE_PAPER_ID
            },
        )
        val stored = runBlocking { store.observeAll().first() }
        assertEquals(
            setOf(BehavioralEventSyncState.SYNCED.value),
            stored.map { it.syncState }.toSet(),
        )
        assertEquals(5, scheduled.get())
    }

    private fun waitForEventCount(
        store: BehavioralEventRepository,
        count: Int,
    ) {
        composeRule.waitUntil(timeoutMillis = 5_000) {
            runBlocking { store.observeAll().first().size == count }
        }
    }
}
