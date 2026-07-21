package com.mneme.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mneme.app.notifications.DigestNotificationChannel
import com.mneme.app.ui.MnemeApp
import com.mneme.app.ui.MnemeViewModel
import com.mneme.app.ui.theme.MnemeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        DigestNotificationChannel.create(this)
        setContent {
            MnemeTheme {
                val mnemeApplication = this@MainActivity.application as MnemeApplication
                val viewModel: MnemeViewModel =
                    viewModel(factory = mnemeApplication.container.viewModelFactory)
                MnemeApp(viewModel = viewModel)
            }
        }
    }
}
