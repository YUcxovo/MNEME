package com.mneme.app.notifications

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.mneme.app.MainActivity

interface DigestNotificationPublisher {
    fun showNewDigest(
        digestId: String,
        digestTitle: String,
    ): Boolean
}

class DigestNotifier(
    private val context: Context,
) : DigestNotificationPublisher {
    override fun showNewDigest(
        digestId: String,
        digestTitle: String,
    ): Boolean {
        DigestNotificationChannel.create(context)
        val notificationManager = NotificationManagerCompat.from(context)
        val runtimePermissionGranted =
            Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    android.Manifest.permission.POST_NOTIFICATIONS,
                ) == PackageManager.PERMISSION_GRANTED
        val channelEnabled =
            Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
                context
                    .getSystemService(NotificationManager::class.java)
                    .getNotificationChannel(DigestNotificationChannel.CHANNEL_ID)
                    ?.importance != NotificationManager.IMPORTANCE_NONE
        if (!runtimePermissionGranted || !notificationManager.areNotificationsEnabled() || !channelEnabled) return false
        val contentIntent =
            PendingIntent.getActivity(
                context,
                REQUEST_CODE_OPEN_APP,
                Intent(context, MainActivity::class.java).apply {
                    action = ACTION_OPEN_DIGEST
                    flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                    putExtra(MainActivity.EXTRA_DIGEST_ID, digestId)
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

        return try {
            notificationManager.notify(NOTIFICATION_ID_NEW_DIGEST, notification)
            true
        } catch (_: SecurityException) {
            false
        }
    }

    private companion object {
        const val REQUEST_CODE_OPEN_APP = 1
        const val NOTIFICATION_ID_NEW_DIGEST = 1
        const val ACTION_OPEN_DIGEST = "com.mneme.app.action.OPEN_DIGEST"
    }
}
