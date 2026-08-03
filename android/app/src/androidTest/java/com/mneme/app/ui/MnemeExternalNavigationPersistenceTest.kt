@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.behavior.QueuedBehavioralEventTracker
import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.MnemeDatabase
import com.mneme.app.data.local.RoomSkeletalCache
import com.mneme.app.data.network.MnemeApiClient
import com.mneme.app.data.repository.NetworkSkeletalDataRepository
import com.mneme.app.ui.navigation.ExternalNavigationRequest
import com.mneme.app.ui.theme.MnemeTheme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

@RunWith(AndroidJUnit4::class)
class MnemeExternalNavigationPersistenceTest {
    @get:Rule
    val composeRule = createComposeRule()

    private lateinit var database: MnemeDatabase
    private lateinit var cache: RoomSkeletalCache
    private lateinit var eventStore: BehavioralEventRepository

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database =
            Room
                .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
                .allowMainThreadQueries()
                .build()
        cache = RoomSkeletalCache(database, MnemeApiClient.json)
        eventStore = BehavioralEventRepository(database.behavioralEventDao())
        runBlocking {
            cache.storeBriefing(
                preferences = BRIEFING_PREFERENCES,
                digest = BRIEFING_DIGEST,
                refreshedAtEpochMillis = FIXED_TIME,
            )
        }
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun offlineCachedPaper_opensOutsideBriefingAndQueuesOneDurableEvent() {
        runBlocking { cache.storePaper(TARGET_PAPER, FIXED_TIME) }
        val networkAvailable = AtomicBoolean(false)
        val scheduledSyncs = AtomicInteger()
        var recompositionToken by mutableIntStateOf(0)

        launchDeepLink(
            networkAvailable = networkAvailable,
            scheduledSyncs = scheduledSyncs,
            modifier = { Modifier.testTag("cached-link-$recompositionToken") },
        )

        waitForText(TARGET_PAPER.title)
        composeRule.onNodeWithText("CACHED BACKEND DATA").assertIsDisplayed()
        waitForTargetOpenEventCount(1)

        composeRule.runOnIdle { recompositionToken += 1 }
        composeRule.waitForIdle()

        assertEquals(1, targetOpenEvents().size)
        assertTrue(scheduledSyncs.get() >= 1)
        assertTrue(BRIEFING_DIGEST.entries.none { it.paper.id == TARGET_PAPER.id })
    }

    @Test
    fun unavailablePaper_recoversThroughRetryAndQueuesEventAfterSuccess() {
        val networkAvailable = AtomicBoolean(false)
        val scheduledSyncs = AtomicInteger()

        launchDeepLink(networkAvailable, scheduledSyncs)

        waitForText("Cannot reach the Mneme backend. Check the API and network, then retry.")
        assertTrue(targetOpenEvents().isEmpty())

        networkAvailable.set(true)
        composeRule.onNodeWithText("Try again").performClick()

        waitForText(TARGET_PAPER.title)
        composeRule.onNodeWithText("LIVE BACKEND DATA").assertIsDisplayed()
        waitForTargetOpenEventCount(1)
        assertEquals(1, targetOpenEvents().size)
        assertTrue(scheduledSyncs.get() >= 1)
    }

    private fun launchDeepLink(
        networkAvailable: AtomicBoolean,
        scheduledSyncs: AtomicInteger,
        modifier: () -> Modifier = { Modifier },
    ) {
        val repository = NetworkSkeletalDataRepository(paperRemote(networkAvailable), cache)
        val tracker =
            QueuedBehavioralEventTracker(
                store = eventStore,
                scheduleSync = { scheduledSyncs.incrementAndGet() },
                nowEpochMillis = { FIXED_TIME },
            )
        val viewModel = MnemeViewModel(repository, tracker)
        var externalRequest by
            mutableStateOf<ExternalNavigationRequest?>(
                ExternalNavigationRequest.OpenPaper(REQUEST_ID, TARGET_PAPER.id),
            )

        composeRule.setContent {
            MnemeTheme {
                MnemeApp(
                    viewModel = viewModel,
                    modifier = modifier(),
                    onOpenSource = {},
                    onSharePaper = { _, _ -> },
                    externalNavigation =
                        MnemeExternalNavigationBinding(
                            request = externalRequest,
                            onRequestConsumed = { requestId ->
                                if (externalRequest?.requestId == requestId) {
                                    externalRequest = null
                                }
                            },
                        ),
                )
            }
        }
    }

    private fun waitForText(text: String) {
        composeRule.waitUntil(timeoutMillis = UI_TIMEOUT_MILLIS) {
            composeRule.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText(text).assertIsDisplayed()
    }

    private fun waitForTargetOpenEventCount(expected: Int) {
        composeRule.waitUntil(timeoutMillis = UI_TIMEOUT_MILLIS) {
            targetOpenEvents().size == expected
        }
    }

    private fun targetOpenEvents() =
        runBlocking {
            eventStore
                .observeAll()
                .first()
                .filter { event ->
                    event.eventType == "paper_opened" && event.paperId == TARGET_PAPER.id
                }
        }
}
