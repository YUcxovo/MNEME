package com.mneme.app.data.network

import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

class BearerTokenInterceptor(
    private val token: String,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val request = chain.request()
        val authenticatedRequest =
            if (request.url.encodedPath.endsWith("/health")) {
                request
            } else {
                request
                    .newBuilder()
                    .header("Authorization", "Bearer $token")
                    .build()
            }
        return chain.proceed(authenticatedRequest)
    }
}

object MnemeApiClient {
    val json: Json =
        Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        }

    fun create(
        baseUrl: String,
        demoToken: String,
    ): MnemeRemoteDataSource {
        require(demoToken.isNotBlank()) { "A non-blank demo token is required for the live API." }
        val normalizedBaseUrl = normalizeBaseUrl(baseUrl)
        val client =
            OkHttpClient
                .Builder()
                .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .writeTimeout(WRITE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .callTimeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .addInterceptor(BearerTokenInterceptor(demoToken))
                .build()
        val retrofit =
            Retrofit
                .Builder()
                .baseUrl(normalizedBaseUrl)
                .client(client)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
        return RetrofitMnemeRemoteDataSource(
            api = retrofit.create(MnemeApi::class.java),
            json = json,
        )
    }

    internal fun normalizeBaseUrl(baseUrl: String): String {
        val trimmed = baseUrl.trim()
        require(trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            "MNEME_API_BASE_URL must use http or https."
        }
        val withSlash = if (trimmed.endsWith('/')) trimmed else "$trimmed/"
        require(withSlash.endsWith("/v1/")) {
            "MNEME_API_BASE_URL must end with /v1/."
        }
        return withSlash
    }
}

sealed interface RemoteResource<out T> {
    data class Ready<T>(
        val value: T,
    ) : RemoteResource<T>

    data class Accepted(
        val job: JobDto,
    ) : RemoteResource<Nothing>
}

@Suppress("TooManyFunctions")
interface MnemeRemoteDataSource {
    suspend fun getHealth(): HealthDto

    suspend fun listPapers(limit: Int = 20): PaperPageDto

    suspend fun getPaper(paperId: String): PaperDto

    suspend fun getPaperSummary(paperId: String): RemoteResource<SummaryDto>

    suspend fun getPreferences(): PreferencesDto

    suspend fun updatePreferences(update: PreferenceUpdateDto): PreferencesDto

    suspend fun initializeFromSeed(request: SeedInitializationRequestDto): SeedInitializationDto

    suspend fun listDigests(limit: Int = 20): DigestPageDto

    suspend fun generateRecommendedDigest(): RemoteResource<DigestDto>

    suspend fun getJob(jobId: String): JobDto

    suspend fun askQuestion(question: QuestionDto): AnswerDto

    suspend fun ingestEvents(events: List<UserEventDto>): EventIngestionResultDto
}

class MnemeApiException(
    val statusCode: Int,
    val errorCode: String,
    override val message: String,
    val requestId: String?,
) : IOException(message)

@Suppress("TooManyFunctions")
internal class RetrofitMnemeRemoteDataSource(
    private val api: MnemeApi,
    private val json: Json,
) : MnemeRemoteDataSource {
    override suspend fun getHealth(): HealthDto = api.getHealth().requireBody(json)

    override suspend fun listPapers(limit: Int): PaperPageDto = api.listPapers(limit = limit).requireBody(json)

    override suspend fun getPaper(paperId: String): PaperDto = api.getPaper(paperId).requireBody(json)

    override suspend fun getPaperSummary(paperId: String): RemoteResource<SummaryDto> =
        api.getPaperSummary(paperId).decodeAcceptedResponse(json)

    override suspend fun getPreferences(): PreferencesDto = api.getPreferences().requireBody(json)

    override suspend fun updatePreferences(update: PreferenceUpdateDto): PreferencesDto {
        val response = api.updatePreferences(update)
        return response.requireBody(json)
    }

    override suspend fun initializeFromSeed(request: SeedInitializationRequestDto): SeedInitializationDto =
        api.initializeFromSeed(request).requireBody(json)

    override suspend fun listDigests(limit: Int): DigestPageDto = api.listDigests(limit = limit).requireBody(json)

    override suspend fun generateRecommendedDigest(): RemoteResource<DigestDto> =
        api.generateRecommendedDigest().decodeAcceptedResponse(json)

    override suspend fun getJob(jobId: String): JobDto = api.getJob(jobId).requireBody(json)

    override suspend fun askQuestion(question: QuestionDto): AnswerDto = api.askQuestion(question).requireBody(json)

    @Suppress("MaxLineLength")
    override suspend fun ingestEvents(events: List<UserEventDto>): EventIngestionResultDto = api.ingestEvents(events).requireBody(json)
}

private fun <T> Response<T>.requireBody(json: Json): T {
    requireSuccessful(json)
    return body() ?: throw SerializationException("The backend returned an empty response body.")
}

private inline fun <reified T> Response<ResponseBody>.decodeAcceptedResponse(json: Json): RemoteResource<T> {
    requireSuccessful(json)
    val payload = requirePayload()
    return when (code()) {
        HTTP_OK -> RemoteResource.Ready(json.decodeFromString<T>(payload))
        HTTP_ACCEPTED -> RemoteResource.Accepted(json.decodeFromString<JobDto>(payload))
        else -> throw SerializationException("The backend returned an unsupported success status.")
    }
}

private fun Response<*>.requireSuccessful(json: Json) {
    if (!isSuccessful) {
        throw apiException(json)
    }
}

private fun Response<ResponseBody>.requirePayload(): String =
    body()?.use(ResponseBody::string)
        ?: throw SerializationException("The backend returned an empty response body.")

private fun Response<*>.apiException(json: Json): MnemeApiException {
    val error =
        errorBody()
            ?.use(ResponseBody::string)
            ?.let { payload ->
                runCatching { json.decodeFromString<ErrorResponseDto>(payload) }.getOrNull()
            }
    return MnemeApiException(
        statusCode = code(),
        errorCode = error?.code ?: "http_error",
        message = error?.message ?: "The Mneme backend rejected the request.",
        requestId = error?.requestId,
    )
}

private const val HTTP_OK = 200
private const val HTTP_ACCEPTED = 202
private const val CONNECT_TIMEOUT_SECONDS = 10L
private const val READ_TIMEOUT_SECONDS = 15 * 60L
private const val WRITE_TIMEOUT_SECONDS = 15L
private const val CALL_TIMEOUT_SECONDS = 15 * 60L
