package com.mneme.app.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.mneme.app.MnemeApplication
import java.time.Duration
import java.util.concurrent.TimeUnit

class DigestSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        val coordinator =
            (applicationContext as? MnemeApplication)
                ?.container
                ?.digestRefreshCoordinator
                ?: return Result.success()
        return when (coordinator.refresh()) {
            is DigestSyncResult.Synced,
            DigestSyncResult.NoCompleteDigest,
            -> Result.success()
            DigestSyncResult.Retry -> Result.retry()
            DigestSyncResult.Failed -> Result.failure()
        }
    }
}

object DigestSyncScheduler {
    const val UNIQUE_WORK_NAME = "digest-periodic-sync"
    const val IMMEDIATE_WORK_NAME = "digest-immediate-sync"
    const val REPEAT_INTERVAL_HOURS = 24L
    const val BACKOFF_DELAY_SECONDS = 30L

    fun schedule(workManager: WorkManager) {
        val request =
            PeriodicWorkRequestBuilder<DigestSyncWorker>(
                Duration.ofHours(REPEAT_INTERVAL_HOURS),
            ).setConstraints(networkConstraints())
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

    fun enqueueNow(workManager: WorkManager) {
        val request =
            OneTimeWorkRequestBuilder<DigestSyncWorker>()
                .setConstraints(networkConstraints())
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    BACKOFF_DELAY_SECONDS,
                    TimeUnit.SECONDS,
                ).build()
        workManager.enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    fun cancel(workManager: WorkManager) {
        workManager.cancelUniqueWork(UNIQUE_WORK_NAME)
        workManager.cancelUniqueWork(IMMEDIATE_WORK_NAME)
    }

    private fun networkConstraints(): Constraints =
        Constraints
            .Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()
}
