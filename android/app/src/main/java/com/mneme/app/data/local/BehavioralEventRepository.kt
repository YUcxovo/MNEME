package com.mneme.app.data.local

import com.mneme.app.data.local.dao.BehavioralEventDao
import com.mneme.app.data.local.entity.BehavioralEventEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

enum class BehavioralEventType {
    PAPER_IMPRESSION,
    PAPER_OPENED,
    PAPER_SAVED,
    PAPER_SKIPPED,
    PAPER_SHARED,
    QUESTION_ASKED,
    DIGEST_DISMISSED,
    ;

    val wireValue: String
        get() = name.lowercase()

    val requiresPaperId: Boolean
        get() = this != DIGEST_DISMISSED
}

interface BehavioralEventStore {
    suspend fun record(
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long? = null,
    ): UUID

    suspend fun recordOnce(
        eventId: UUID,
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long? = null,
    ): UUID

    suspend fun reservePendingBatch(
        limit: Int,
        attemptedAtEpochMillis: Long,
        staleBeforeEpochMillis: Long,
    ): List<BehavioralEventEntity>

    suspend fun markBatchSynced(eventIds: List<UUID>)

    suspend fun returnBatchToPending(
        eventIds: List<UUID>,
        error: String?,
    )
}

class BehavioralEventRepository(
    private val behavioralEventDao: BehavioralEventDao,
    private val idGenerator: () -> UUID = UUID::randomUUID,
) : BehavioralEventStore {
    fun observeAll(): Flow<List<BehavioralEventEntity>> = behavioralEventDao.observeAll()

    override suspend fun record(
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long?,
    ): UUID {
        validateEvent(type, paperId, occurredAtEpochMillis, durationMillis)

        val eventId = idGenerator()
        behavioralEventDao.insert(
            eventEntity(eventId, type, paperId, occurredAtEpochMillis, durationMillis),
        )
        return eventId
    }

    override suspend fun recordOnce(
        eventId: UUID,
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long?,
    ): UUID {
        validateEvent(type, paperId, occurredAtEpochMillis, durationMillis)
        val requested = eventEntity(eventId, type, paperId, occurredAtEpochMillis, durationMillis)
        val inserted = behavioralEventDao.insertIfAbsent(requested)
        if (inserted == INSERT_IGNORED) {
            val existing = behavioralEventDao.findById(eventId.toString())
            check(
                existing != null &&
                    existing.eventType == requested.eventType &&
                    existing.paperId == requested.paperId &&
                    existing.durationMillis == requested.durationMillis,
            ) {
                "An existing behavioral event uses the requested UUID for another payload."
            }
        }
        return eventId
    }

    private fun validateEvent(
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long?,
    ) {
        require(type.requiresPaperId == (paperId != null)) {
            if (type.requiresPaperId) {
                "${type.wireValue} events require an internal paper UUID."
            } else {
                "${type.wireValue} events cannot reference a paper."
            }
        }
        require(durationMillis == null || type == BehavioralEventType.PAPER_OPENED) {
            "Only paper_opened events can include a duration."
        }
        require(durationMillis == null || durationMillis >= 0) {
            "Event duration cannot be negative."
        }
        require(durationMillis == null || durationMillis <= Int.MAX_VALUE) {
            "Event duration exceeds the frozen API limit."
        }
        require(occurredAtEpochMillis >= 0) {
            "Event occurrence time cannot precede the Unix epoch."
        }
    }

    private fun eventEntity(
        eventId: UUID,
        type: BehavioralEventType,
        paperId: UUID?,
        occurredAtEpochMillis: Long,
        durationMillis: Long?,
    ) = BehavioralEventEntity(
        id = eventId.toString(),
        eventType = type.wireValue,
        paperId = paperId?.toString(),
        occurredAtEpochMillis = occurredAtEpochMillis,
        durationMillis = durationMillis,
    )

    override suspend fun reservePendingBatch(
        limit: Int,
        attemptedAtEpochMillis: Long,
        staleBeforeEpochMillis: Long,
    ): List<BehavioralEventEntity> {
        require(limit > 0) { "Batch limit must be positive." }
        require(attemptedAtEpochMillis >= 0) { "Attempt time cannot be negative." }
        require(staleBeforeEpochMillis in 0..attemptedAtEpochMillis) {
            "Stale cutoff must be between the Unix epoch and the attempt time."
        }
        return behavioralEventDao.reservePendingBatch(
            limit = limit,
            attemptedAtEpochMillis = attemptedAtEpochMillis,
            staleBeforeEpochMillis = staleBeforeEpochMillis,
        )
    }

    override suspend fun markBatchSynced(eventIds: List<UUID>) {
        if (eventIds.isNotEmpty()) {
            behavioralEventDao.markSynced(eventIds.map(UUID::toString))
        }
    }

    override suspend fun returnBatchToPending(
        eventIds: List<UUID>,
        error: String?,
    ) {
        if (eventIds.isNotEmpty()) {
            behavioralEventDao.markPending(eventIds.map(UUID::toString), error)
        }
    }

    private companion object {
        const val INSERT_IGNORED = -1L
    }
}
