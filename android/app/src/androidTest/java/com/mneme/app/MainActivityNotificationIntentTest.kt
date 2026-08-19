package com.mneme.app

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.ui.navigation.ExternalNavigationRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityNotificationIntentTest {
    @Test
    fun coldStart_notificationIntentIsAcceptedOnce() {
        val scenario = ActivityScenario.launch<MainActivity>(notificationIntent("digest-cold"))

        scenario.onActivity { activity ->
            assertFalse(activity.intent.hasExtra(MainActivity.EXTRA_DIGEST_ID))
        }
        scenario.close()
    }

    @Test
    fun alreadyOpenActivity_notificationIntentReplacesDigestTarget() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java))

        scenario.onActivity { activity ->
            activity.acceptExternalIntent(notificationIntent("digest-warm"))
            assertEquals(
                "digest-warm",
                (activity.externalRequestForTest() as ExternalNavigationRequest.OpenDigest).digestId,
            )
        }
        scenario.close()
    }

    private fun notificationIntent(digestId: String): Intent {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_DIGEST_ID, digestId)
    }
}
