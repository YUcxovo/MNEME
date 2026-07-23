package com.mneme.app.data.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class HealthDto(
    val status: String,
)

@Serializable
data class PaperDto(
    val id: String,
    @SerialName("arxiv_id") val arxivId: String,
    val title: String,
    val authors: List<String>,
    val abstract: String,
    @SerialName("primary_category") val primaryCategory: String,
    val categories: List<String>,
    @SerialName("pdf_url") val pdfUrl: String,
    @SerialName("processing_status") val processingStatus: String,
    @SerialName("published_at") val publishedAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class PaperPageDto(
    val items: List<PaperDto>,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class SummaryDto(
    @SerialName("paper_id") val paperId: String,
    val status: String,
    val tldr: String,
    @SerialName("key_claims") val keyClaims: List<String> = emptyList(),
    val methodology: String? = null,
    val limitations: String? = null,
    @SerialName("source_match_status") val sourceMatchStatus: String,
)

@Serializable
data class PreferencesDto(
    val topics: List<String>,
    @SerialName("followed_authors") val followedAuthors: List<String>,
    @SerialName("model_version") val modelVersion: Int,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class PreferenceUpdateDto(
    val topics: List<String>,
    @SerialName("followed_authors") val followedAuthors: List<String>,
)

@Serializable
data class SeedInitializationRequestDto(
    @SerialName("arxiv_reference") val arxivReference: String,
)

@Serializable
data class SeedInitializationDto(
    @SerialName("seed_arxiv_id") val seedArxivId: String,
    val category: String,
    @SerialName("paper_count") val paperCount: Int,
    val preferences: PreferencesDto,
    val digest: DigestDto,
)

@Serializable
data class DigestEntryDto(
    val paper: PaperDto,
    val rank: Int,
    @SerialName("relevance_score") val relevanceScore: Double,
    @SerialName("recommendation_reason") val recommendationReason: String,
)

@Serializable
data class DigestDto(
    val id: String,
    @SerialName("digest_type") val digestType: String,
    @SerialName("generated_at") val generatedAt: String,
    val entries: List<DigestEntryDto>,
)

@Serializable
data class DigestPageDto(
    val items: List<DigestDto>,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

const val QUESTION_MAX_LENGTH = 500

@Serializable
data class QuestionDto(
    val question: String,
    @SerialName("paper_id") val paperId: String,
    @SerialName("conversation_id") val conversationId: String? = null,
)

@Serializable
data class CitationDto(
    @SerialName("paper_id") val paperId: String,
    @SerialName("arxiv_id") val arxivId: String? = null,
    @SerialName("section_title") val sectionTitle: String,
    @SerialName("chunk_id") val chunkId: String? = null,
    @SerialName("source_match") val sourceMatch: Boolean,
)

@Serializable
data class AnswerDto(
    val answer: String,
    val citations: List<CitationDto>,
    @SerialName("source_match_status") val sourceMatchStatus: String,
    @SerialName("conversation_id") val conversationId: String,
)

@Serializable
data class GraphNodeDto(
    val id: String,
    val title: String,
    val category: String? = null,
    @SerialName("cluster_id") val clusterId: String? = null,
    @SerialName("rank_score") val rankScore: Double? = null,
)

@Serializable
data class GraphEdgeDto(
    val source: String,
    val target: String,
    val weight: Double? = null,
)

@Serializable
data class GraphDto(
    @SerialName("center_id") val centerId: String,
    val nodes: List<GraphNodeDto>,
    val edges: List<GraphEdgeDto>,
    @SerialName("algorithm_status") val algorithmStatus: String,
    @SerialName("graph_version") val graphVersion: String? = null,
)

@Serializable
data class JobDto(
    val id: String,
    val stage: String,
    val status: String,
    @SerialName("error_code") val errorCode: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class UserEventDto(
    @SerialName("event_id") val eventId: String,
    @SerialName("event_type") val eventType: String,
    @SerialName("paper_id") val paperId: String? = null,
    @SerialName("occurred_at") val occurredAt: String,
    @SerialName("duration_ms") val durationMillis: Long? = null,
)

@Serializable
data class EventIngestionResultDto(
    val accepted: Int,
    val duplicates: Int,
)

@Serializable
data class ErrorResponseDto(
    val code: String,
    val message: String,
    @SerialName("request_id") val requestId: String,
    val details: JsonObject? = null,
)
