package com.mneme.app.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.time.Duration
import java.util.concurrent.TimeUnit

class DigestSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        // The remote repository will be connected when the API client is available.
        return Result.success()
    }
}

object DigestSyncScheduler {
    const val UNIQUE_WORK_NAME = "digest-periodic-sync"
    const val REPEAT_INTERVAL_HOURS = 24L
    const val BACKOFF_DELAY_SECONDS = 30L

    fun schedule(workManager: WorkManager) {
        val constraints =
            Constraints
                .Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .setRequiresBatteryNotLow(true)
                .build()
        val request =
            PeriodicWorkRequestBuilder<DigestSyncWorker>(
                Duration.ofHours(REPEAT_INTERVAL_HOURS),
            ).setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    BACKOFF_DELAY_SECONDS,
                    TimeUnit.SECONDS,
                ).build()

        workManager.enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun cancel(workManager: WorkManager) {
        workManager.cancelUniqueWork(UNIQUE_WORK_NAME)
    }
}
