package com.hirestack.ai.data.network

import com.squareup.moshi.JsonClass

/**
 * Mirrors backend `/api/auth/me` response.
 * Loose schema — backend returns the raw user row plus runtime fields.
 */
@JsonClass(generateAdapter = true)
data class MeResponse(
    val id: String? = null,
    val email: String? = null,
    val full_name: String? = null,
    val avatar_url: String? = null,
    val role: String? = null,
)

@JsonClass(generateAdapter = true)
data class VerifyResponse(
    val valid: Boolean,
    val uid: String? = null,
    val email: String? = null,
    val name: String? = null,
)
