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

// ---- Tier 3: Profiles + ATS + Document Library ----

/**
 * Mirrors a row from `/api/profile` (list) — backend returns the raw resume_profiles
 * row which has many optional columns. We surface the most useful summary fields.
 */
@JsonClass(generateAdapter = true)
data class Profile(
    val id: String,
    val user_id: String? = null,
    val full_name: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val location: String? = null,
    val headline: String? = null,
    val summary: String? = null,
    val is_primary: Boolean? = null,
    val source_filename: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

/**
 * Body for `POST /api/ats/scan`.
 */
@JsonClass(generateAdapter = true)
data class AtsScanRequest(
    val document_content: String,
    val jd_text: String,
    val document_id: String? = null,
    val job_id: String? = null,
)

/**
 * Mirrors success_response wrapper used by `/api/ats/scan`.
 */
@JsonClass(generateAdapter = true)
data class AtsScanResponse(
    val success: Boolean = true,
    val data: AtsScan? = null,
)

/**
 * One ATS scan row — both `POST /scan` (inside `data`) and `GET /ats` items
 * use this shape. All numeric fields are optional because some backends return
 * them as ints, others as floats.
 */
@JsonClass(generateAdapter = true)
data class AtsScan(
    val id: String? = null,
    val ats_score: Int = 0,
    val keyword_match_rate: Double? = null,
    val readability_score: Double? = null,
    val format_score: Double? = null,
    val matched_keywords: List<String> = emptyList(),
    val missing_keywords: List<String> = emptyList(),
    val document_id: String? = null,
    val job_id: String? = null,
    val created_at: String? = null,
)

/**
 * Mirrors `GET /api/documents/library/all` response.
 */
@JsonClass(generateAdapter = true)
data class DocumentLibraryListResponse(
    val documents: List<DocumentLibraryItem> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class DocumentLibraryItem(
    val id: String,
    val doc_type: String? = null,
    val doc_category: String? = null,
    val label: String? = null,
    val status: String? = null,
    val version: Int? = null,
    val source: String? = null,
    val application_id: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class DocumentLibraryItemResponse(
    val document: DocumentLibraryItem? = null,
)
