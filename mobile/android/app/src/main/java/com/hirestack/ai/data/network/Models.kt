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

// ---- Tier 2: Dashboard + Jobs ----

/**
 * Mirrors backend `/api/analytics/dashboard` response from
 * `app/services/analytics.py::get_dashboard`.
 */
@JsonClass(generateAdapter = true)
data class DashboardResponse(
    val applications: Int = 0,
    val active_applications: Int = 0,
    val profiles: Int = 0,
    val jobs_analyzed: Int = 0,
    val evidence_items: Int = 0,
    val total_tasks: Int = 0,
    val completed_tasks: Int = 0,
    val latest_score: Double? = null,
    val ats_scans: Int = 0,
    val salary_analyses: Int = 0,
    val interview_sessions: Int = 0,
    val learning_streak: Int = 0,
    val summary: DashboardSummary? = null,
)

@JsonClass(generateAdapter = true)
data class DashboardSummary(
    val has_profile: Boolean = false,
    val has_application: Boolean = false,
    val has_evidence: Boolean = false,
    val task_completion_rate: Double = 0.0,
)

/**
 * Mirrors backend job rows. Backend stores rich JSON; we only
 * surface the fields needed for the mobile board + detail screen.
 */
@JsonClass(generateAdapter = true)
data class Job(
    val id: String,
    val user_id: String? = null,
    val title: String,
    val company: String? = null,
    val location: String? = null,
    val job_type: String? = null,
    val experience_level: String? = null,
    val salary_range: String? = null,
    val description: String? = null,
    val source_url: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

/**
 * Body for `POST /jobs`.
 */
@JsonClass(generateAdapter = true)
data class CreateJobRequest(
    val title: String,
    val company: String? = null,
    val location: String? = null,
    val job_type: String? = null,
    val experience_level: String? = null,
    val salary_range: String? = null,
    val description: String? = null,
    val source_url: String? = null,
)
