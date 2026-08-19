package com.mneme.app.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.WorkManager
import com.mneme.app.sync.DigestSyncScheduler

/** Local debug hook that asks the production WorkManager path to check for a new digest. */
class DigestSyncDemoReceiver : BroadcastReceiver() {
    override fun onReceive(
        context: Context,
        intent: Intent,
    ) {
        if (intent.action != ACTION_TRIGGER_DIGEST_SYNC) return
        DigestSyncScheduler.enqueueNow(WorkManager.getInstance(context.applicationContext))
    }

    companion object {
        const val ACTION_TRIGGER_DIGEST_SYNC =
            "com.mneme.app.debug.action.TRIGGER_DIGEST_SYNC"
    }
}
