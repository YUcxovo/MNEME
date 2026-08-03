package com.mneme.app.ui

import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import com.mneme.app.R

@Composable
internal fun rememberExternalActions(callbacks: MnemeExternalCallbacks): MnemeExternalActions {
    val uriHandler = LocalUriHandler.current
    val context = LocalContext.current
    val sourceOpener = callbacks.openSource ?: { url: String -> uriHandler.openUri(url) }
    val paperSharer =
        callbacks.sharePaper ?: { title: String, url: String ->
            val sendIntent =
                Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, title)
                    putExtra(Intent.EXTRA_TEXT, "$title\n$url")
                }
            context.startActivity(
                Intent.createChooser(
                    sendIntent,
                    context.getString(R.string.share_chooser_title),
                ),
            )
        }
    return MnemeExternalActions(
        openSource = sourceOpener,
        sharePaper = paperSharer,
    )
}
