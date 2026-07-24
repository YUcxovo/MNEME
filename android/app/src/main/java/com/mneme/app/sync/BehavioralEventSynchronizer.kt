package com.mneme.app.sync

import com.mneme.app.data.local.BehavioralEventRepository
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.MnemeRemoteDataSource
import com.mneme.app.data.network.UserEventDto
import java.time.Instant
import java.util.UUID

class BehavioralEventSynchronizer(
    private val repository: BehavioralEventRepository,
    private val remote: MnemeRemoteDataSource,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) {
    suspend fun sync(): Outcome {
        val now = nowEpochMillis()
        val events = repository.reservePendingBatch(BATCH_LIMIT, now, now - STALE_IN_FLIGHT_MILLIS)
        if (events.isEmpty()) return Outcome.Success
        return try {
            val result = remote.ingestEvents(events.map(BehavioralEventEntity::toDto))
            check(result.accepted + result.duplicates == events.size) {
                "The events API did not account for the complete batch."
            }
            repository.markBatchSynced(events.map { UUID.fromString(it.id) })
            Outcome.Success
        } catch (error: MnemeApiException) {
            repository.returnBatchToPending(events.map { UUID.fromString(it.id) }, error.message)
            if (error.statusCode >= SERVER_ERROR_MIN_STATUS) Outcome.Retry else Outcome.Failure
        } catch (error: java.io.IOException) {
            repository.returnBatchToPending(events.map { UUID.fromString(it.id) }, error.message)
            Outcome.Retry
        }
    }

    sealed interface Outcome {
        data object Success : Outcome

        data object Retry : Outcome

        data object Failure : Outcome
    }

    companion object {
        const val BATCH_LIMIT = 500
        private const val SERVER_ERROR_MIN_STATUS = 500
        private const val STALE_IN_FLIGHT_MILLIS = 15 * 60 * 1000L
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
