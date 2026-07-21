package com.mneme.app.data.network

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface MnemeApi {
    @GET("health")
    suspend fun getHealth(): Response<HealthDto>

    @GET("papers")
    suspend fun listPapers(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): Response<PaperPageDto>

    @GET("papers/{paper_id}")
    suspend fun getPaper(
        @Path("paper_id") paperId: String,
    ): Response<PaperDto>

    @GET("papers/{paper_id}/summary")
    suspend fun getPaperSummary(
        @Path("paper_id") paperId: String,
    ): Response<ResponseBody>

    @GET("users/me/preferences")
    suspend fun getPreferences(): Response<PreferencesDto>

    @PUT("users/me/preferences")
    suspend fun updatePreferences(
        @Body update: PreferenceUpdateDto,
    ): Response<PreferencesDto>

    @GET("digests")
    suspend fun listDigests(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): Response<DigestPageDto>

    @POST("digests/recommended")
    suspend fun generateRecommendedDigest(): Response<ResponseBody>

    @GET("jobs/{job_id}")
    suspend fun getJob(
        @Path("job_id") jobId: String,
    ): Response<JobDto>

    @POST("qa/ask")
    suspend fun askQuestion(
        @Body question: QuestionDto,
    ): Response<AnswerDto>
}
