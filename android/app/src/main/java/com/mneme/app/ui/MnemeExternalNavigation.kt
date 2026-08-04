@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import android.content.Intent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.mneme.app.R
import com.mneme.app.ui.navigation.ExternalNavigationRequest

data class MnemeExternalNavigationBinding(
    val request: ExternalNavigationRequest? = null,
    val onRequestConsumed: (Long) -> Unit = {},
)

internal data class MnemeExternalActions(
    val openSource: (String) -> Unit,
    val sharePaper: (String, String) -> Unit,
)

internal data class MnemeExternalEnvironment(
    val navigation: MnemeExternalNavigationBinding,
    val snackbarHostState: SnackbarHostState,
    val actions: MnemeExternalActions,
)

@Composable
internal fun rememberMnemeExternalEnvironment(
    openSourceOverride: ((String) -> Unit)?,
    sharePaperOverride: ((String, String) -> Unit)?,
    navigation: MnemeExternalNavigationBinding,
): MnemeExternalEnvironment {
    val snackbarHostState = remember { SnackbarHostState() }
    val invalidLinkMessage = stringResource(R.string.paper_deep_link_invalid)
    val uriHandler = LocalUriHandler.current
    val context = LocalContext.current
    val sourceOpener = openSourceOverride ?: { url: String -> uriHandler.openUri(url) }
    val paperSharer =
        sharePaperOverride ?: { title: String, shareText: String ->
            context.startActivity(
                Intent.createChooser(
                    paperShareIntent(title, shareText),
                    context.getString(R.string.share_chooser_title),
                ),
            )
        }

    LaunchedEffect(navigation.request) {
        val request = navigation.request
        if (request is ExternalNavigationRequest.InvalidPaperLink) {
            snackbarHostState.currentSnackbarData?.dismiss()
            snackbarHostState.showSnackbar(invalidLinkMessage)
            navigation.onRequestConsumed(request.requestId)
        }
    }

    return MnemeExternalEnvironment(
        navigation = navigation,
        snackbarHostState = snackbarHostState,
        actions = MnemeExternalActions(openSource = sourceOpener, sharePaper = paperSharer),
    )
}

@Composable
internal fun restoreNotificationBriefing(
    onboardingState: OnboardingUiState,
    request: ExternalNavigationRequest?,
    openBriefingDigest: (String) -> Unit,
) {
    LaunchedEffect(request) {
        if (request is ExternalNavigationRequest.OpenDigest && onboardingState != OnboardingUiState.Ready) {
            openBriefingDigest(request.digestId)
        }
    }
}

internal fun paperShareIntent(
    title: String,
    shareText: String,
): Intent =
    Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_SUBJECT, title)
        putExtra(Intent.EXTRA_TEXT, shareText)
    }

@Composable
internal fun OnboardingWithSnackbar(
    snackbarHostState: SnackbarHostState,
    content: @Composable () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        content()
        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
        )
    }
}
