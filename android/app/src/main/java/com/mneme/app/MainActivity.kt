package com.mneme.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
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

class MainActivity : ComponentActivity() {
    private val externalNavigation: ExternalNavigationViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        DigestNotificationChannel.create(this)
        if (savedInstanceState == null) {
            acceptExternalIntent(intent)
        }
        setContent {
            MnemeTheme {
                val mnemeApplication = this@MainActivity.application as MnemeApplication
                val viewModel: MnemeViewModel =
                    viewModel(factory = mnemeApplication.container.viewModelFactory)
                val externalRequest = externalNavigation.request.collectAsStateWithLifecycle()
                mnemeApp(
                    viewModel = viewModel,
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
        acceptExternalIntent(intent)
    }

    internal fun acceptExternalIntent(intent: Intent) {
        if (intent.action != Intent.ACTION_VIEW) {
            return
        }
        val paperId = intent.dataString?.let(PaperDeepLink::parseUri)
        if (paperId == null) {
            externalNavigation.rejectPaperLink()
        } else {
            externalNavigation.openPaper(paperId)
        }
    }
}
