package com.mneme.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.mneme.app.notifications.DigestNotificationChannel
import com.mneme.app.ui.MnemeApp
import com.mneme.app.ui.theme.MnemeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        DigestNotificationChannel.create(this)
        setContent {
            MnemeTheme {
                MnemeApp()
            }
        }
    }
}
