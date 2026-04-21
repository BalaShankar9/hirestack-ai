package com.hirestack.ai.data.network

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface HireStackApi {
    // Auth
    @GET("auth/verify")
    suspend fun verify(): VerifyResponse

    @GET("auth/me")
    suspend fun me(): MeResponse

    // Dashboard
    @GET("analytics/dashboard")
    suspend fun dashboard(): DashboardResponse

    // Jobs
    @GET("jobs")
    suspend fun listJobs(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
    ): List<Job>

    @GET("jobs/{id}")
    suspend fun getJob(@Path("id") id: String): Job

    @POST("jobs")
    suspend fun createJob(@Body body: CreateJobRequest): Job

    @DELETE("jobs/{id}")
    suspend fun deleteJob(@Path("id") id: String)

    // Profiles
    @GET("profile")
    suspend fun listProfiles(): List<Profile>

    @GET("profile/{id}")
    suspend fun getProfile(@Path("id") id: String): Profile

    @DELETE("profile/{id}")
    suspend fun deleteProfile(@Path("id") id: String)

    @POST("profile/{id}/set-primary")
    suspend fun setPrimaryProfile(@Path("id") id: String)

    // ATS Scanner
    @GET("ats")
    suspend fun listAtsScans(): List<AtsScan>

    @POST("ats/scan")
    suspend fun runAtsScan(@Body body: AtsScanRequest): AtsScanResponse

    // Document Library
    @GET("documents/library/all")
    suspend fun listDocuments(
        @Query("limit") limit: Int = 100,
        @Query("category") category: String? = null,
    ): DocumentLibraryListResponse

    @GET("documents/library/{id}")
    suspend fun getDocument(@Path("id") id: String): DocumentLibraryItemResponse

    // Candidates (recruiter pipeline)
    @GET("candidates")
    suspend fun listCandidates(
        @Query("stage") stage: String? = null,
    ): List<Candidate>

    @GET("candidates/{id}")
    suspend fun getCandidate(@Path("id") id: String): Candidate

    // Interview Coach
    @GET("interview/sessions")
    suspend fun listInterviewSessions(): List<InterviewSession>

    @GET("interview/sessions/{id}")
    suspend fun getInterviewSession(@Path("id") id: String): InterviewSession
}
