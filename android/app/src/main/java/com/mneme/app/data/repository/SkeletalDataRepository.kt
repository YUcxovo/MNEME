package com.mneme.app.data.repository

import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.local.SkeletalCache
import com.mneme.app.data.network.MnemeApiException
import com.mneme.app.data.network.MnemeRemoteDataSource
import com.mneme.app.data.network.PreferenceUpdateDto
import com.mneme.app.data.network.QUESTION_MAX_LENGTH
import com.mneme.app.data.network.QuestionDto
import com.mneme.app.data.network.RemoteResource
import com.mneme.app.data.network.SeedInitializationRequestDto
import com.mneme.app.data.network.findDigest
import com.mneme.app.ui.model.BriefingUiModel
import com.mneme.app.ui.model.ContentOrigin
import com.mneme.app.ui.model.GraphUiModel
import com.mneme.app.ui.model.PaperDetailUiModel
import com.mneme.app.ui.model.QaUiModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.SerializationException
import java.io.IOException

sealed interface PaperContentResult {
    data class Ready(
        val paper: PaperDetailUiModel,
    ) : PaperContentResult

    data class Processing(
        val paperId: String,
        val jobId: String,
        val stage: String,
    ) : PaperContentResult
}

interface SkeletalDataRepository {
    suspend fun restoreBriefing(): BriefingUiModel?

    suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel

    suspend fun loadBriefing(): BriefingUiModel

    suspend fun loadBriefing(digestId: String): BriefingUiModel = loadBriefing()

    suspend fun updateInterests(topics: List<String>): BriefingUiModel

    suspend fun loadPaper(paperId: String): PaperContentResult

    suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult

    suspend fun askQuestion(
        paperId: String,
        question: String,
        conversationId: String? = null,
    ): QaUiModel

    suspend fun loadGraph(paperId: String): GraphUiModel
}

class ControlledFixtureDataRepository : SkeletalDataRepository {
    private var topics = SeededSkeletalContentRepository.briefing().interests

    override suspend fun restoreBriefing(): BriefingUiModel = loadBriefing()

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel = loadBriefing()

    override suspend fun loadBriefing(): BriefingUiModel = currentBriefing()

    override suspend fun loadBriefing(digestId: String): BriefingUiModel = currentBriefing()

    override suspend fun updateInterests(topics: List<String>): BriefingUiModel {
        this.topics = normalizeTopics(topics)
        return loadBriefing()
    }

    private fun currentBriefing(): BriefingUiModel = SeededSkeletalContentRepository.briefing().copy(interests = topics)

    override suspend fun loadPaper(paperId: String): PaperContentResult =
        SeededSkeletalContentRepository.paper(paperId)?.let(PaperContentResult::Ready)
            ?: throw ContentUnavailableException("The selected paper is not available.")

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult = loadPaper(paperId)

    override suspend fun askQuestion(
        paperId: String,
        question: String,
        conversationId: String?,
    ): QaUiModel =
        SeededSkeletalContentRepository
            .qa(paperId, question)
            ?.copy(conversationId = conversationId ?: "controlled-$paperId")
            ?: throw ContentUnavailableException("A paper-specific answer is not available.")

    override suspend fun loadGraph(paperId: String): GraphUiModel =
        SeededSkeletalContentRepository.graph(paperId)
            ?: throw ContentUnavailableException("A citation graph is not available for this paper.")
}

class NetworkSkeletalDataRepository(
    private val remote: MnemeRemoteDataSource,
    private val cache: SkeletalCache,
    private val nowEpochMillis: () -> Long = System::currentTimeMillis,
) : SkeletalDataRepository {
    override suspend fun restoreBriefing(): BriefingUiModel? = cache.getBriefing()?.toRestoredBriefing()

    override suspend fun initializeFromSeed(arxivReference: String): BriefingUiModel {
        require(arxivReference.isNotBlank()) { "An arXiv URL or identifier is required." }
        val result =
            remote.initializeFromSeed(
                SeedInitializationRequestDto(arxivReference = arxivReference.trim()),
            )
        val refreshedAt = nowEpochMillis()
        cache.storeBriefing(result.preferences, result.digest, refreshedAt)
        return result.digest.toBriefing(
            interests = result.preferences.topics,
            disclosure =
                disclosure(
                    ContentOrigin.LIVE_BACKEND,
                    "Five papers prepared from seed ${result.seedArxivId}.",
                ),
        )
    }

    override suspend fun loadBriefing(): BriefingUiModel =
        try {
            val (preferences, digestResult) =
                coroutineScope {
                    val preferences = async { remote.getPreferences() }
                    val digest = async { remote.generateRecommendedDigest() }
                    preferences.await() to digest.await()
                }
            val digest =
                when (digestResult) {
                    is RemoteResource.Ready -> digestResult.value
                    is RemoteResource.Accepted -> {
                        throw ContentPendingException(
                            "The research briefing is still being prepared. Try again shortly.",
                        )
                    }
                }
            val refreshedAt = nowEpochMillis()
            cache.storeBriefing(preferences, digest, refreshedAt)
            digest.toBriefing(
                interests = preferences.topics,
                disclosure =
                    disclosure(
                        ContentOrigin.LIVE_BACKEND,
                        "Recommendations use the configured demo profile.",
                    ),
            )
        } catch (error: IOException) {
            cache.getBriefing()?.toBriefing() ?: throw error
        } catch (error: SerializationException) {
            cache.getBriefing()?.toBriefing() ?: throw error
        }

    override suspend fun loadBriefing(digestId: String): BriefingUiModel {
        require(digestId.isNotBlank()) { "A digest identifier is required." }
        return try {
            val (preferences, digest) =
                coroutineScope {
                    val preferences = async { remote.getPreferences() }
                    val digest = async { remote.findDigest { it.id == digestId } }
                    preferences.await() to digest.await()
                }
            val target =
                digest ?: throw ContentUnavailableException(
                    "This research briefing is no longer available.",
                )
            val refreshedAt = nowEpochMillis()
            cache.storeBriefing(preferences, target, refreshedAt)
            target.toBriefing(
                interests = preferences.topics,
                disclosure =
                    disclosure(
                        ContentOrigin.LIVE_BACKEND,
                        "Opened the research briefing selected from the notification.",
                    ),
            )
        } catch (error: IOException) {
            cache.getBriefing(digestId)?.toBriefing() ?: throw error
        } catch (error: SerializationException) {
            cache.getBriefing(digestId)?.toBriefing() ?: throw error
        }
    }

    override suspend fun updateInterests(topics: List<String>): BriefingUiModel {
        val normalized = normalizeTopics(topics)
        val current = remote.getPreferences()
        val updated =
            remote.updatePreferences(
                PreferenceUpdateDto(
                    topics = normalized,
                    followedAuthors = current.followedAuthors,
                ),
            )
        val digest =
            when (val result = remote.generateRecommendedDigest()) {
                is RemoteResource.Ready -> result.value
                is RemoteResource.Accepted ->
                    throw ContentPendingException(
                        "The updated research briefing is still being prepared. Try saving again shortly.",
                    )
            }
        val refreshedAt = nowEpochMillis()
        cache.storeBriefing(updated, digest, refreshedAt)
        return digest.toBriefing(
            interests = updated.topics,
            disclosure =
                disclosure(
                    ContentOrigin.LIVE_BACKEND,
                    "Recommendations use your updated research interests.",
                ),
        )
    }

    override suspend fun loadPaper(paperId: String): PaperContentResult =
        try {
            val paper = remote.getPaper(paperId)
            if (paper.id != paperId) {
                throw SerializationException(
                    "The backend paper ID does not match the requested paper.",
                )
            }
            val refreshedAt = nowEpochMillis()
            cache.storePaper(paper, refreshedAt)
            cache.markPaperOpened(paperId, refreshedAt)
            when (val summary = remote.getPaperSummary(paperId)) {
                is RemoteResource.Ready -> PaperContentResult.Ready(paper.toDetail(summary.value))
                is RemoteResource.Accepted ->
                    PaperContentResult.Processing(
                        paperId = paperId,
                        jobId = summary.job.id,
                        stage = summary.job.stage,
                    )
            }
        } catch (error: IOException) {
            cache.getPaper(paperId)?.toCachedDetail() ?: throw error
        } catch (error: SerializationException) {
            cache.getPaper(paperId)?.toCachedDetail() ?: throw error
        }

    override suspend fun refreshPaper(
        paperId: String,
        jobId: String,
    ): PaperContentResult {
        val job = remote.getJob(jobId)
        return when (job.status) {
            "queued", "running" ->
                PaperContentResult.Processing(
                    paperId = paperId,
                    jobId = job.id,
                    stage = job.stage,
                )
            "succeeded" -> loadPaper(paperId)
            "failed" ->
                throw ContentUnavailableException(
                    "The backend could not prepare this paper summary. Retry the paper to start recovery.",
                )
            else ->
                throw SerializationException(
                    "The backend returned an unknown pipeline job status.",
                )
        }
    }

    override suspend fun askQuestion(
        paperId: String,
        question: String,
        conversationId: String?,
    ): QaUiModel {
        require(question.isNotBlank()) { "Question must not be blank." }
        require(question.length <= QUESTION_MAX_LENGTH) {
            "Question must not exceed $QUESTION_MAX_LENGTH characters."
        }
        val paper = cache.getPaper(paperId) ?: remote.getPaper(paperId).toCachedPaper()
        val answer =
            remote.askQuestion(
                QuestionDto(
                    question = question,
                    paperId = paperId,
                    conversationId = conversationId,
                ),
            )
        return answer.toQa(
            paper = paper,
            question = question,
            requestedConversationId = conversationId,
        )
    }

    override suspend fun loadGraph(paperId: String): GraphUiModel {
        require(paperId.isNotBlank()) { "A paper identifier is required." }
        return remote
            .getPaperGraph(
                paperId = paperId,
                depth = GRAPH_DEPTH,
                limit = GRAPH_NODE_LIMIT,
            ).toGraphUi()
    }

    private companion object {
        const val GRAPH_DEPTH = 2
        const val GRAPH_NODE_LIMIT = 50
    }
}

internal fun normalizeTopics(topics: List<String>): List<String> {
    require(topics.size <= MAX_INTEREST_TOPICS) {
        "No more than $MAX_INTEREST_TOPICS research interests are allowed."
    }
    val normalized = mutableListOf<String>()
    val seen = mutableSetOf<String>()
    topics.forEach { topic ->
        val trimmed = topic.trim()
        require(trimmed.isNotEmpty()) { "Research interests cannot be blank." }
        require(trimmed.length <= MAX_INTEREST_LENGTH) {
            "Each research interest must not exceed $MAX_INTEREST_LENGTH characters."
        }
        if (seen.add(trimmed.lowercase())) {
            normalized += trimmed
        }
    }
    return normalized
}

private const val MAX_INTEREST_TOPICS = 100
private const val MAX_INTEREST_LENGTH = 100

class ContentPendingException(
    message: String,
) : IOException(message)

class ContentUnavailableException(
    message: String,
) : IOException(message)

fun Throwable.toUserMessage(): String =
    when (this) {
        is MnemeApiException -> message
        is ContentPendingException, is ContentUnavailableException ->
            message ?: "The requested content is unavailable."
        is SerializationException ->
            "The backend response does not match the frozen v0.1 API contract."
        is IOException ->
            "Cannot reach the Mneme backend. Check the API and network, then retry."
        else -> "The requested content could not be loaded."
    }
