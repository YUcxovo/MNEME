@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityDeepLinkTest {
    private val coldLaunchIntent = paperIntent(SeededSkeletalContentRepository.PAPER_ID)
    private val activityRule = ActivityScenarioRule<MainActivity>(coldLaunchIntent)

    @get:Rule
    val composeRule =
        AndroidComposeTestRule(activityRule) { rule ->
            lateinit var activity: MainActivity
            rule.scenario.onActivity { activity = it }
            activity
        }

    @Before
    fun requireControlledFixtureBuild() {
        check(BuildConfig.MNEME_DEMO_TOKEN.isBlank()) {
            "MainActivityDeepLinkTest requires the controlled-fixture Android build."
        }
    }

    @Test
    fun coldAndWarmPaperIntents_routeInOneActivity_andMalformedIntentIsRecoverable() {
        assertManifestResolvesPaperLink()
        val coldActivity = composeRule.activity

        // A cold ACTION_VIEW launch resolves through the normal repository-backed paper path.
        waitForText("Attention Is All You Need")
        assertEquals(coldLaunchIntent.dataString, coldActivity.intent.dataString)

        // Deliver a second valid link through Android while MainActivity is already on top.
        // The manifest launch policy must retain the Activity and onNewIntent must load the
        // requested paper; the test does not inject CLEAR_TOP or SINGLE_TOP flags.
        val warmLaunchIntent = paperIntent(SeededSkeletalContentRepository.NEIGHBOR_PAPER_ID)
        targetContext().startActivity(warmLaunchIntent.asWarmDelivery())
        waitForActivityIntent(warmLaunchIntent.dataString)
        waitForText("Attention predecessor")
        assertSame(coldActivity, composeRule.activity)

        // A malformed warm link reports the contract error without replacing the current
        // paper detail or creating another Activity instance.
        val malformedIntent = paperIntent("not-a-canonical-uuid")
        targetContext().startActivity(malformedIntent.asWarmDelivery())
        waitForActivityIntent(malformedIntent.dataString)
        waitForText("This Mneme paper link is invalid.")
        composeRule.onNodeWithText("Attention predecessor").assertIsDisplayed()
        assertSame(coldActivity, composeRule.activity)

        // The requested paper replaces any previous detail destination. Returning from the
        // malformed-link snackbar therefore reaches the single briefing start destination,
        // rather than revealing the earlier cold-start paper underneath it.
        composeRule.onNodeWithTag("navigate-back").performClick()
        composeRule.onNodeWithTag("briefing-screen").assertIsDisplayed()

        // ActivityScenario identifies its Activity by the launch Intent. MainActivity
        // correctly replaces that Intent in onNewIntent, so restore the test harness's
        // launch value before the rule closes the same Activity.
        composeRule.runOnIdle { coldActivity.intent = coldLaunchIntent }
    }

    private fun waitForText(text: String) {
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText(text).assertIsDisplayed()
    }

    private fun waitForActivityIntent(dataString: String?) {
        composeRule.waitUntil(timeoutMillis = 5_000) {
            composeRule.activity.intent.dataString == dataString
        }
    }

    private fun assertManifestResolvesPaperLink() {
        val context = targetContext()
        val implicitIntent =
            Intent(
                Intent.ACTION_VIEW,
                Uri.parse("mneme://paper/${SeededSkeletalContentRepository.PAPER_ID}"),
            ).apply {
                addCategory(Intent.CATEGORY_DEFAULT)
                addCategory(Intent.CATEGORY_BROWSABLE)
                setPackage(context.packageName)
            }
        val matches =
            context.packageManager.queryIntentActivities(
                implicitIntent,
                android.content.pm.PackageManager.MATCH_DEFAULT_ONLY,
            )
        assertTrue(
            "The DEFAULT/BROWSABLE paper-link filter must resolve MainActivity.",
            matches.any { it.activityInfo.name == MainActivity::class.java.name },
        )
    }
}

private fun paperIntent(paperId: String): Intent =
    Intent(Intent.ACTION_VIEW, Uri.parse("mneme://paper/$paperId")).apply {
        addCategory(Intent.CATEGORY_BROWSABLE)
        setPackage(targetContext().packageName)
    }

private fun Intent.asWarmDelivery(): Intent = addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

private fun targetContext(): Context = ApplicationProvider.getApplicationContext()
