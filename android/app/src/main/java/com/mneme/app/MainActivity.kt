package com.mneme.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.activity.viewModels
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mneme.app.notifications.DigestNotificationChannel
import com.mneme.app.ui.MnemeExternalNavigationBinding
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.mnemeApp
import com.mneme.app.ui.navigation.ExternalNavigationViewModel
import com.mneme.app.ui.navigation.PaperDeepLink
import com.mneme.app.ui.theme.MnemeTheme
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {
    private val externalNavigation: ExternalNavigationViewModel by viewModels()
    private val notificationDigestId = MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        receiveNotificationIntent(intent)
        enableEdgeToEdge()
        DigestNotificationChannel.create(this)
        if (savedInstanceState == null) {
            acceptExternalIntent(intent)
        }
        setContent {
            MnemeTheme {
                val digestId by notificationDigestId.collectAsStateWithLifecycle()
                val mnemeApplication = this@MainActivity.application as MnemeApplication
                val viewModel: MnemeViewModel =
                    viewModel(factory = mnemeApplication.container.viewModelFactory)
                val externalRequest = externalNavigation.request.collectAsStateWithLifecycle()
                mnemeApp(
                    viewModel = viewModel,
                    notificationDigestId = digestId,
                    externalNavigation =
                        MnemeExternalNavigationBinding(
                            request = externalRequest.value,
                            onRequestConsumed = externalNavigation::consume,
                        ),
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        receiveNotificationIntent(intent)
        acceptExternalIntent(intent)
    }

    internal fun acceptExternalIntent(intent: Intent) {
        if (
            intent.action != Intent.ACTION_VIEW ||
            intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0
        ) {
            return
        }
        val paperId = intent.dataString?.let(PaperDeepLink::parseUri)
        if (paperId == null) {
            externalNavigation.rejectPaperLink()
        } else {
            externalNavigation.openPaper(paperId)
        }
    }

    internal fun receiveNotificationIntent(intent: Intent?) {
        notificationDigestId.value = intent?.getStringExtra(EXTRA_DIGEST_ID)?.takeIf(String::isNotBlank)
    }

    internal fun notificationDigestIdForTest(): String? = notificationDigestId.value

    companion object {
        const val EXTRA_DIGEST_ID = "com.mneme.app.extra.DIGEST_ID"
    }
}
