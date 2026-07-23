package com.mneme.app.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.mneme.app.MnemeApplication
import com.mneme.app.data.behavior.BehavioralEventSyncResult
import java.util.concurrent.TimeUnit

class BehavioralEventSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        val coordinator =
            (applicationContext as? MnemeApplication)
                ?.container
                ?.behavioralEventSyncCoordinator
        val syncResult = coordinator?.syncPending()
        return when (syncResult) {
            null,
            BehavioralEventSyncResult.Idle,
            is BehavioralEventSyncResult.Synced,
            -> Result.success()
            is BehavioralEventSyncResult.Retry -> Result.retry()
        }
    }
}

object BehavioralEventSyncScheduler {
    const val UNIQUE_WORK_NAME = "behavioral-event-sync"
    const val BACKOFF_DELAY_SECONDS = 30L

    fun enqueue(workManager: WorkManager) {
        val constraints =
            Constraints
                .Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
        val request =
            OneTimeWorkRequestBuilder<BehavioralEventSyncWorker>()
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    BACKOFF_DELAY_SECONDS,
                    TimeUnit.SECONDS,
                ).build()
        workManager.enqueueUniqueWork(
            UNIQUE_WORK_NAME,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }
}
