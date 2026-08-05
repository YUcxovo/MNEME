package com.mneme.app.data.local

import androidx.room.withTransaction
import com.mneme.app.data.local.entity.CacheMetadataEntity
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.local.entity.PaperEntity
import com.mneme.app.data.local.entity.UserPrefsEntity
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PreferencesDto
import com.mneme.app.data.network.SummaryDto
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.time.Instant

data class CachedBriefing(
    val digest: DigestEntity,
    val description: String,
    val interests: List<String>,
    val papers: List<CachedPaper>,
    val recommendationReasons: Map<String, String>,
    val refreshedAtEpochMillis: Long,
)

data class CachedPaper(
    val id: String,
    val arxivId: String,
    val title: String,
    val authors: List<String>,
    val abstractText: String,
    val primaryCategory: String?,
    val pdfUrl: String?,
    val processingStatus: String,
    val updatedAtEpochMillis: Long,
    val summary: SummaryDto? = null,
)

interface SkeletalCache {
    suspend fun storeBriefing(
        preferences: PreferencesDto,
        digest: DigestDto,
        refreshedAtEpochMillis: Long,
    )

    suspend fun getBriefing(): CachedBriefing?

    suspend fun getBriefing(digestId: String): CachedBriefing? = getBriefing()?.takeIf { it.digest.id == digestId }

    suspend fun storePaper(
        paper: PaperDto,
        refreshedAtEpochMillis: Long,
    )

    suspend fun storePaperContent(
        paper: PaperDto,
        summary: SummaryDto,
        refreshedAtEpochMillis: Long,
    ) {
        storePaper(paper, refreshedAtEpochMillis)
    }

    suspend fun getPaper(paperId: String): CachedPaper?

    suspend fun markPaperOpened(
        paperId: String,
        openedAtEpochMillis: Long,
    )
}

class RoomSkeletalCache(
    private val database: MnemeDatabase,
    private val json: Json,
) : SkeletalCache {
    override suspend fun storeBriefing(
        preferences: PreferencesDto,
        digest: DigestDto,
        refreshedAtEpochMillis: Long,
    ) {
        val payload =
            CachedDigestPayload(
                description = digest.description(),
                paperIds = digest.entries.sortedBy { it.rank }.map { it.paper.id },
                recommendationReasons =
                    digest.entries.associate { entry ->
                        entry.paper.id to entry.recommendationReason
                    },
            )
        database.withTransaction {
            val existingPapers = database.paperDao().getAll().associateBy(PaperEntity::id)
            database.paperDao().upsertAll(
                digest.entries.map { entry ->
                    entry.paper.toEntity(
                        lastSyncedAtEpochMillis = refreshedAtEpochMillis,
                        json = json,
                        summaryJson = existingPapers[entry.paper.id]?.summaryJson,
                        lastOpenedAtEpochMillis =
                            existingPapers[entry.paper.id]?.lastOpenedAtEpochMillis ?: 0,
                    )
                },
            )
            database.digestDao().upsertAll(
                listOf(
                    DigestEntity(
                        id = digest.id,
                        title = digest.title(),
                        summary = json.encodeToString(CachedDigestPayload.serializer(), payload),
                        digestType = digest.digestType,
                        generatedAtEpochMillis = digest.generatedAt.toEpochMillis(refreshedAtEpochMillis),
                        lastSyncedAtEpochMillis = refreshedAtEpochMillis,
                    ),
                ),
            )
            database.userPrefsDao().upsert(preferences.toEntity(refreshedAtEpochMillis, json))
            database.cacheMetadataDao().upsert(
                CacheMetadataEntity(lastSuccessfulRefreshAtEpochMillis = refreshedAtEpochMillis),
            )
        }
    }

    override suspend fun getBriefing(): CachedBriefing? {
        val digest = database.digestDao().getLatest()
        return digest?.let { cachedDigest -> readBriefing(cachedDigest) }
    }

    override suspend fun getBriefing(digestId: String): CachedBriefing? {
        val digest = database.digestDao().getById(digestId)
        return digest?.let { readBriefing(it) }
    }

    private suspend fun readBriefing(digest: DigestEntity): CachedBriefing? {
        val payload =
            runCatching {
                json.decodeFromString(CachedDigestPayload.serializer(), digest.summary)
            }.getOrElse {
                CachedDigestPayload(
                    description = digest.summary,
                    paperIds = database.paperDao().getAll().map(PaperEntity::id),
                    recommendationReasons = emptyMap(),
                )
            }
        val papersById = database.paperDao().getAll().associateBy(PaperEntity::id)
        val papers =
            payload.paperIds
                .mapNotNull(papersById::get)
                .map { paper -> paper.toCachedPaper(json) }
        val preferences = database.userPrefsDao().get(DEMO_USER_CACHE_ID)
        val topics =
            preferences
                ?.topicsJson
                ?.let { encoded -> runCatching { json.decodeFromString<List<String>>(encoded) }.getOrNull() }
                .orEmpty()
        val refreshedAt =
            database.cacheMetadataDao().get()?.lastSuccessfulRefreshAtEpochMillis
                ?: digest.lastSyncedAtEpochMillis
        return if (papers.isEmpty() && payload.paperIds.isNotEmpty()) {
            null
        } else {
            CachedBriefing(
                digest = digest,
                description = payload.description,
                interests = topics,
                papers = papers,
                recommendationReasons = payload.recommendationReasons,
                refreshedAtEpochMillis = refreshedAt,
            )
        }
    }

    override suspend fun storePaper(
        paper: PaperDto,
        refreshedAtEpochMillis: Long,
    ) {
        database.withTransaction {
            val existing = database.paperDao().getById(paper.id)
            database.paperDao().upsertAll(
                listOf(
                    paper.toEntity(
                        lastSyncedAtEpochMillis = refreshedAtEpochMillis,
                        json = json,
                        summaryJson = existing?.summaryJson,
                        lastOpenedAtEpochMillis = existing?.lastOpenedAtEpochMillis ?: 0,
                    ),
                ),
            )
        }
    }

    override suspend fun storePaperContent(
        paper: PaperDto,
        summary: SummaryDto,
        refreshedAtEpochMillis: Long,
    ) {
        require(summary.paperId == paper.id) {
            "A cached summary must belong to the cached paper."
        }
        database.withTransaction {
            val existing = database.paperDao().getById(paper.id)
            database.paperDao().upsertAll(
                listOf(
                    paper.toEntity(
                        lastSyncedAtEpochMillis = refreshedAtEpochMillis,
                        json = json,
                        summaryJson = json.encodeToString(SummaryDto.serializer(), summary),
                        lastOpenedAtEpochMillis = existing?.lastOpenedAtEpochMillis ?: 0,
                    ),
                ),
            )
        }
    }

    override suspend fun getPaper(paperId: String): CachedPaper? {
        val entity = database.paperDao().getById(paperId)
        return entity?.toCachedPaper(json)
    }

    override suspend fun markPaperOpened(
        paperId: String,
        openedAtEpochMillis: Long,
    ) {
        database.paperDao().markOpened(paperId, openedAtEpochMillis)
    }

    companion object {
        const val DEMO_USER_CACHE_ID = "demo-user"
    }
}

@Serializable
private data class CachedDigestPayload(
    val description: String,
    val paperIds: List<String>,
    val recommendationReasons: Map<String, String>,
)

private fun DigestDto.title(): String =
    when (digestType) {
        "weekly" -> "Weekly research briefing"
        "manual" -> "Research briefing for your current topics"
        else -> "Research briefing"
    }

private fun DigestDto.description(): String =
    when (entries.size) {
        0 -> "No papers are available for this briefing yet."
        1 -> "One paper prepared for this briefing."
        else -> "${entries.size} papers prepared for this briefing."
    }

private fun PaperDto.toEntity(
    lastSyncedAtEpochMillis: Long,
    json: Json,
    summaryJson: String? = null,
    lastOpenedAtEpochMillis: Long = 0,
): PaperEntity =
    PaperEntity(
        id = id,
        arxivId = arxivId,
        title = title,
        authorsJson = json.encodeToString(authors),
        abstractText = abstract,
        primaryCategory = primaryCategory,
        pdfUrl = pdfUrl,
        processingStatus = processingStatus,
        updatedAtEpochMillis = updatedAt.toEpochMillis(lastSyncedAtEpochMillis),
        lastSyncedAtEpochMillis = lastSyncedAtEpochMillis,
        lastOpenedAtEpochMillis = lastOpenedAtEpochMillis,
        summaryJson = summaryJson,
    )

private fun PreferencesDto.toEntity(
    lastSyncedAtEpochMillis: Long,
    json: Json,
): UserPrefsEntity =
    UserPrefsEntity(
        userId = RoomSkeletalCache.DEMO_USER_CACHE_ID,
        topicsJson = json.encodeToString(topics),
        keywordsJson = json.encodeToString(followedAuthors),
        notificationsEnabled = true,
        updatedAtEpochMillis =
            updatedAt?.toEpochMillis(lastSyncedAtEpochMillis)
                ?: lastSyncedAtEpochMillis,
        lastSyncedAtEpochMillis = lastSyncedAtEpochMillis,
    )

private fun PaperEntity.toCachedPaper(json: Json): CachedPaper =
    CachedPaper(
        id = id,
        arxivId = arxivId,
        title = title,
        authors =
            runCatching { json.decodeFromString<List<String>>(authorsJson) }
                .getOrDefault(emptyList()),
        abstractText = abstractText,
        primaryCategory = primaryCategory,
        pdfUrl = pdfUrl,
        processingStatus = processingStatus,
        updatedAtEpochMillis = updatedAtEpochMillis,
        summary =
            summaryJson
                ?.let { encoded ->
                    runCatching {
                        json.decodeFromString(SummaryDto.serializer(), encoded)
                    }.getOrNull()
                }?.takeIf { summary -> summary.paperId == id },
    )

private fun String.toEpochMillis(fallback: Long): Long {
    val parsed = runCatching { Instant.parse(this).toEpochMilli() }
    return parsed.getOrDefault(fallback)
}
