package com.mneme.app.data.local

import androidx.room.withTransaction
import com.mneme.app.data.local.entity.CacheMetadataEntity
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.local.entity.PaperEntity
import com.mneme.app.data.local.entity.UserPrefsEntity
import com.mneme.app.data.network.DigestDto
import com.mneme.app.data.network.PaperDto
import com.mneme.app.data.network.PreferencesDto
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
)

interface SkeletalCache {
    suspend fun storeBriefing(
        preferences: PreferencesDto,
        digest: DigestDto,
        refreshedAtEpochMillis: Long,
    )

    suspend fun getBriefing(): CachedBriefing?

    suspend fun storePaper(
        paper: PaperDto,
        refreshedAtEpochMillis: Long,
    )

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
            database.paperDao().upsertAll(
                digest.entries.map { entry ->
                    entry.paper.toEntity(refreshedAtEpochMillis, json)
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
            database.userPrefsDao().upsert(
                UserPrefsEntity(
                    userId = DEMO_USER_CACHE_ID,
                    topicsJson = json.encodeToString(preferences.topics),
                    keywordsJson = json.encodeToString(preferences.followedAuthors),
                    notificationsEnabled = true,
                    updatedAtEpochMillis =
                        preferences.updatedAt?.toEpochMillis(refreshedAtEpochMillis)
                            ?: refreshedAtEpochMillis,
                    lastSyncedAtEpochMillis = refreshedAtEpochMillis,
                ),
            )
            database.cacheMetadataDao().upsert(
                CacheMetadataEntity(lastSuccessfulRefreshAtEpochMillis = refreshedAtEpochMillis),
            )
        }
    }

    override suspend fun getBriefing(): CachedBriefing? {
        val digest = database.digestDao().getLatest()
        return digest?.let { cachedDigest -> readBriefing(cachedDigest) }
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
        database.paperDao().upsertAll(listOf(paper.toEntity(refreshedAtEpochMillis, json)))
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
        0 -> "No papers currently match the configured demo profile."
        1 -> "One paper selected from the current backend catalog."
        else -> "${entries.size} papers selected from the current backend catalog."
    }

private fun PaperDto.toEntity(
    lastSyncedAtEpochMillis: Long,
    json: Json,
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
    )

private fun String.toEpochMillis(fallback: Long): Long {
    val parsed = runCatching { Instant.parse(this).toEpochMilli() }
    return parsed.getOrDefault(fallback)
}
