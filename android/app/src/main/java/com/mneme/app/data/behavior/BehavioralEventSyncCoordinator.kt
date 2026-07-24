package com.mneme.app.data.behavior

import com.mneme.app.data.local.BehavioralEventStore
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.network.BehavioralEventRemoteDataSource
import com.mneme.app.data.network.EventIngestionResultDto
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.UserEventDto
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import java.io.IOException
import java.time.Instant
import java.util.UUID

sealed interface BehavioralEventSyncResult {
    data object Idle : BehavioralEventSyncResult

    data class Synced(
        val processed: Int,
        val accepted: Int,
        val duplicates: Int,
    ) : BehavioralEventSyncResult

    data class Retry(
        val reason: String,
    ) : BehavioralEventSyncResult

    data class Failed(
        val reason: String,
    ) : BehavioralEventSyncResult
}

private sealed interface BatchUploadResult {
    data class Synced(
        val accepted: Int,
        val duplicates: Int,
    ) : BatchUploadResult

    data class Retry(
        val reason: String,
    ) : BatchUploadResult

    data class Failed(
        val reason: String,
    ) : BatchUploadResult
}

private sealed interface UploadAttempt {
    data class Response(
        val result: EventIngestionResultDto,
    ) : UploadAttempt

    data class Failure(
        val reason: String,
        val retryable: Boolean,
    ) : UploadAttempt
}

class BehavioralEventSyncCoordinator(
    private val store: BehavioralEventStore,
    private val remote: BehavioralEventRemoteDataSource,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) {
    suspend fun syncPending(): BehavioralEventSyncResult {
        var processed = 0
        var accepted = 0
        var duplicates = 0
        var completedBatches = 0
        var outcome: BehavioralEventSyncResult? = null
        while (completedBatches < MAX_BATCHES_PER_RUN && outcome == null) {
            val attemptedAt = nowEpochMillis()
            require(attemptedAt >= 0) { "Sync time cannot precede the Unix epoch." }
            val batch =
                store.reservePendingBatch(
                    limit = BATCH_SIZE,
                    attemptedAtEpochMillis = attemptedAt,
                    staleBeforeEpochMillis = (attemptedAt - STALE_AFTER_MILLIS).coerceAtLeast(0),
                )
            if (batch.isEmpty()) {
                outcome =
                    when {
                        processed == 0 -> BehavioralEventSyncResult.Idle
                        else -> BehavioralEventSyncResult.Synced(processed, accepted, duplicates)
                    }
            } else {
                when (val batchResult = uploadBatch(batch)) {
                    is BatchUploadResult.Synced -> {
                        processed += batch.size
                        accepted += batchResult.accepted
                        duplicates += batchResult.duplicates
                        completedBatches += 1
                    }
                    is BatchUploadResult.Retry -> {
                        outcome = BehavioralEventSyncResult.Retry(batchResult.reason)
                    }
                    is BatchUploadResult.Failed -> {
                        outcome = BehavioralEventSyncResult.Failed(batchResult.reason)
                    }
                }
            }
        }
        return outcome ?: BehavioralEventSyncResult.Retry(BATCH_LIMIT_REACHED)
    }

    private suspend fun uploadBatch(batch: List<BehavioralEventEntity>): BatchUploadResult {
        val eventIds = batch.map { UUID.fromString(it.id) }
        val attempt =
            try {
                UploadAttempt.Response(remote.uploadEvents(batch.map(BehavioralEventEntity::toDto)))
            } catch (error: CancellationException) {
                store.returnBatchToPending(eventIds, SYNC_CANCELLED)
                throw error
            } catch (error: MnemeApiException) {
                UploadAttempt.Failure(
                    reason = "api_${error.statusCode}",
                    retryable = error.statusCode >= SERVER_ERROR_MIN_STATUS,
                )
            } catch (_: SerializationException) {
                UploadAttempt.Failure(SERIALIZATION_ERROR, retryable = true)
            } catch (_: IOException) {
                UploadAttempt.Failure(NETWORK_ERROR, retryable = true)
            }
        return when (attempt) {
            is UploadAttempt.Response ->
                if (attempt.result.matches(batch.size)) {
                    store.markBatchSynced(eventIds)
                    BatchUploadResult.Synced(attempt.result.accepted, attempt.result.duplicates)
                } else {
                    store.returnBatchToPending(eventIds, INVALID_RESULT)
                    BatchUploadResult.Retry(INVALID_RESULT)
                }
            is UploadAttempt.Failure -> {
                store.returnBatchToPending(eventIds, attempt.reason)
                if (attempt.retryable) {
                    BatchUploadResult.Retry(attempt.reason)
                } else {
                    BatchUploadResult.Failed(attempt.reason)
                }
            }
        }
    }

    companion object {
        const val BATCH_SIZE = 50
        const val MAX_BATCHES_PER_RUN = 10
        const val STALE_AFTER_MILLIS = 15 * 60 * 1_000L

        const val BATCH_LIMIT_REACHED = "batch_limit_reached"
        const val INVALID_RESULT = "invalid_ingestion_result"
        const val NETWORK_ERROR = "network_error"
        const val SERIALIZATION_ERROR = "serialization_error"
        const val SYNC_CANCELLED = "sync_cancelled"

        private const val SERVER_ERROR_MIN_STATUS = 500
    }
}

private fun BehavioralEventEntity.toDto(): UserEventDto =
    UserEventDto(
        eventId = id,
        eventType = eventType,
        paperId = paperId,
        occurredAt = Instant.ofEpochMilli(occurredAtEpochMillis).toString(),
        durationMillis = durationMillis,
    )

private fun EventIngestionResultDto.matches(batchSize: Int): Boolean =
    accepted >= 0 && duplicates >= 0 && accepted + duplicates == batchSize
