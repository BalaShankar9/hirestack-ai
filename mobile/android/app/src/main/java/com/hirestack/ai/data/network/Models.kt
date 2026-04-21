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

// ---- Tier 4: Candidates (pipeline) + Interview Coach ----

/**
 * Mirrors a row from `/api/candidates` (recruiter / org-scoped).
 */
@JsonClass(generateAdapter = true)
data class Candidate(
    val id: String,
    val org_id: String? = null,
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    val location: String? = null,
    val client_company: String? = null,
    val pipeline_stage: String? = null,
    val tags: List<String> = emptyList(),
    val notes: String? = null,
    val assigned_recruiter: String? = null,
    val status: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

/**
 * Mirrors a row from `/api/interview/sessions`.
 */
@JsonClass(generateAdapter = true)
data class InterviewSession(
    val id: String,
    val user_id: String? = null,
    val job_title: String? = null,
    val company: String? = null,
    val difficulty: String? = null,
    val interview_type: String? = null,
    val status: String? = null,
    val question_count: Int? = null,
    val average_score: Double? = null,
    val overall_score: Double? = null,
    val questions: List<InterviewQuestion> = emptyList(),
    val answers: List<InterviewAnswer> = emptyList(),
    val created_at: String? = null,
    val expires_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class InterviewQuestion(
    val id: String? = null,
    val question: String? = null,
    val category: String? = null,
    val difficulty: String? = null,
)

@JsonClass(generateAdapter = true)
data class InterviewAnswer(
    val question_id: String? = null,
    val answer_text: String? = null,
    val score: Double? = null,
    val feedback: String? = null,
)

// ---- Tier 5: Career analytics + Learning + Salary ----

/**
 * `/api/career/portfolio` — backend returns a free-form dict. We pull the most
 * useful summary fields out, keeping unknown ones as a raw map elsewhere.
 */
@JsonClass(generateAdapter = true)
data class CareerPortfolio(
    val total_applications: Int? = null,
    val active_applications: Int? = null,
    val total_evidence: Int? = null,
    val skills_count: Int? = null,
    val current_score: Double? = null,
    val streak_days: Int? = null,
    val last_activity: String? = null,
)

/**
 * `/api/career/timeline` — list of dated snapshots.
 */
@JsonClass(generateAdapter = true)
data class CareerSnapshot(
    val date: String? = null,
    val captured_at: String? = null,
    val applications: Int? = null,
    val active_applications: Int? = null,
    val score: Double? = null,
    val evidence: Int? = null,
)

/**
 * `/api/career/outcomes/funnel` — counts by stage.
 */
@JsonClass(generateAdapter = true)
data class ConversionFunnel(
    val exported: Int = 0,
    val applied: Int = 0,
    val screened: Int = 0,
    val interview: Int = 0,
    val interview_done: Int = 0,
    val offer: Int = 0,
    val accepted: Int = 0,
    val rejected: Int = 0,
)

/**
 * `/api/learning/streak` — streak summary.
 */
@JsonClass(generateAdapter = true)
data class LearningStreak(
    val user_id: String? = null,
    val current_streak: Int = 0,
    val longest_streak: Int = 0,
    val last_active_date: String? = null,
    val total_challenges: Int = 0,
    val total_correct: Int = 0,
)

/**
 * Items returned from `/api/learning/today` and `/api/learning/history`.
 */
@JsonClass(generateAdapter = true)
data class LearningChallenge(
    val id: String,
    val skill: String? = null,
    val difficulty: String? = null,
    val question: String? = null,
    val answer: String? = null,
    val user_answer: String? = null,
    val score: Double? = null,
    val is_correct: Boolean? = null,
    val completed: Boolean? = null,
    val created_at: String? = null,
)

/**
 * `/api/salary/` — a row from the user's salary analyses list.
 */
@JsonClass(generateAdapter = true)
data class SalaryAnalysis(
    val id: String,
    val job_title: String? = null,
    val company: String? = null,
    val location: String? = null,
    val experience_years: Double? = null,
    val current_salary: Double? = null,
    val market_low: Double? = null,
    val market_median: Double? = null,
    val market_high: Double? = null,
    val recommended_target: Double? = null,
    val negotiation_script: String? = null,
    val created_at: String? = null,
)

// ---- Tier 6: Variants + Knowledge ----

@JsonClass(generateAdapter = true)
data class DocVariant(
    val id: String,
    val application_id: String? = null,
    val document_type: String? = null,
    val variant_name: String? = null,
    val tone: String? = null,
    val content: String? = null,
    val word_count: Int? = null,
    val ats_score: Double? = null,
    val readability_score: Double? = null,
    val is_selected: Boolean? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class SelectVariantResponse(
    val status: String? = null,
    val variant_id: String? = null,
)
@JsonClass(generateAdapter = true)
data class KnowledgeResource(
    val id: String,
    val title: String? = null,
    val description: String? = null,
    val category: String? = null,
    val resource_type: String? = null,
    val difficulty: String? = null,
    val skills: List<String>? = null,
    val url: String? = null,
    val author: String? = null,
    val duration_minutes: Int? = null,
    val is_featured: Boolean? = null,
)

/**
 * `/api/knowledge/progress` — user progress row with embedded resource.
 */
@JsonClass(generateAdapter = true)
data class KnowledgeProgress(
    val id: String? = null,
    val resource_id: String? = null,
    val status: String? = null,
    val progress_pct: Int? = null,
    val rating: Int? = null,
    val updated_at: String? = null,
    val knowledge_resources: KnowledgeResource? = null,
)

/**
 * `/api/knowledge/recommendations` — embedded resource via Supabase join.
 */
@JsonClass(generateAdapter = true)
data class KnowledgeRecommendation(
    val id: String,
    val resource_id: String? = null,
    val reason: String? = null,
    val relevance_score: Double? = null,
    val is_dismissed: Boolean? = null,
    val knowledge_resources: KnowledgeResource? = null,
)
