package com.mneme.app.notifications

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.mneme.app.MainActivity

class DigestNotifier(
    private val context: Context,
) {
    fun showNewDigest(digestTitle: String): Boolean {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(
                context,
                android.Manifest.permission.POST_NOTIFICATIONS,
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }

        DigestNotificationChannel.create(context)
        val contentIntent =
            PendingIntent.getActivity(
                context,
                REQUEST_CODE_OPEN_APP,
                Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                },
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        val notification =
            NotificationCompat
                .Builder(context, DigestNotificationChannel.CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_popup_reminder)
                .setContentTitle("New Research Briefing")
                .setContentText(digestTitle)
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .build()

        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID_NEW_DIGEST, notification)
        return true
    }

    private companion object {
        const val REQUEST_CODE_OPEN_APP = 1
        const val NOTIFICATION_ID_NEW_DIGEST = 1
    }
}
