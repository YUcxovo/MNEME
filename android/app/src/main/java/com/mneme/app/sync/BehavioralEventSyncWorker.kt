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
import com.mneme.app.MnemeApplication
import java.time.Duration
import java.util.concurrent.TimeUnit

class BehavioralEventSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        val synchronizer =
            (applicationContext as MnemeApplication).container.behavioralEventSynchronizer
                ?: return Result.success()
        return when (synchronizer.sync()) {
            BehavioralEventSynchronizer.Outcome.Success -> Result.success()
            BehavioralEventSynchronizer.Outcome.Retry -> Result.retry()
            BehavioralEventSynchronizer.Outcome.Failure -> Result.failure()
        }
    }
}

object BehavioralEventSyncScheduler {
    private const val UNIQUE_WORK_NAME = "behavioral-event-sync"

    fun schedule(workManager: WorkManager) {
        val requestBuilder = PeriodicWorkRequestBuilder<BehavioralEventSyncWorker>(Duration.ofHours(1))
        requestBuilder.setConstraints(
            Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build(),
        )
        requestBuilder.setBackoffCriteria(BackoffPolicy.EXPONENTIAL, INITIAL_BACKOFF_SECONDS, TimeUnit.SECONDS)
        val request = requestBuilder.build()
        workManager.enqueueUniquePeriodicWork(UNIQUE_WORK_NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
    }

    private const val INITIAL_BACKOFF_SECONDS = 30L
}
