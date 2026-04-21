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
}
