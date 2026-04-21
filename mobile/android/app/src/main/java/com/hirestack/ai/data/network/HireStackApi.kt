package com.hirestack.ai.data.network

import retrofit2.http.GET

interface HireStackApi {
    @GET("auth/verify")
    suspend fun verify(): VerifyResponse

    @GET("auth/me")
    suspend fun me(): MeResponse
}
