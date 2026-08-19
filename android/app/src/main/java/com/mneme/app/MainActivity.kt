package com.mneme.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.work.WorkManager
import com.mneme.app.notifications.DigestNotificationChannel
import com.mneme.app.sync.DigestSyncScheduler
import com.mneme.app.ui.MnemeExternalNavigationBinding
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.mnemeApp
import com.mneme.app.ui.navigation.ExternalNavigationRequest
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
                requestNotificationPermission()
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
        if (intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0) {
            return
        }
        val digestId = intent.getStringExtra(EXTRA_DIGEST_ID)?.takeIf(String::isNotBlank)
        when {
            digestId != null -> {
                externalNavigation.openDigest(digestId)
                intent.removeExtra(EXTRA_DIGEST_ID)
            }
            intent.action == Intent.ACTION_VIEW -> {
                val paperId = intent.dataString?.let(PaperDeepLink::parseUri)
                if (paperId == null) {
                    externalNavigation.rejectPaperLink()
                } else {
                    externalNavigation.openPaper(paperId)
                }
            }
        }
    }

    internal fun externalRequestForTest(): ExternalNavigationRequest? = externalNavigation.request.value

    companion object {
        const val EXTRA_DIGEST_ID = "com.mneme.app.extra.DIGEST_ID"
    }
}

@Composable
private fun requestNotificationPermission() {
    if (
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        BuildConfig.MNEME_DEMO_TOKEN.isBlank()
    ) {
        return
    }
    val context = LocalContext.current
    val launcher =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                DigestSyncScheduler.enqueueNow(WorkManager.getInstance(context))
            }
        }
    LaunchedEffect(Unit) {
        if (
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS,
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}
