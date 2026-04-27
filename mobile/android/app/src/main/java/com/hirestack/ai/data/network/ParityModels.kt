package com.hirestack.ai.data.network

import com.squareup.moshi.JsonClass

/**
 * Models added in Tier 9 (parity pass) — covering applications, generation
 * jobs, evidence, gaps, skills, benchmarks, builder, consultant, exports,
 * orgs, billing, api keys, and richer dashboard payloads.
 *
 * Schema notes:
 * - All fields nullable / defaulted because the backend stores most of these
 *   as JSONB and the shape evolves. The mobile UI degrades gracefully on
 *   missing fields rather than crashing.
 * - Keys are snake_case to match PostgREST + FastAPI without custom name
 *   adapters.
 */

/* ============================================================
 * Applications (read via Supabase PostgREST, write via /generate/jobs)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class Application(
    val id: String,
    val user_id: String? = null,
    val title: String? = null,
    val status: String? = null,
    val job_title: String? = null,
    val company: String? = null,
    val location: String? = null,
    val jd_text: String? = null,
    val jd_quality: JdQualityShape? = null,
    val confirmed_facts: ConfirmedFacts? = null,
    val facts_locked: Boolean? = null,
    val modules: Map<String, ModuleStatusEntry>? = null,
    val benchmark: Map<String, Any?>? = null,
    val gaps: Map<String, Any?>? = null,
    val learning_plan: Map<String, Any?>? = null,
    val cv_html: String? = null,
    val cover_letter_html: String? = null,
    val personal_statement_html: String? = null,
    val portfolio_html: String? = null,
    val resume_html: String? = null,
    val scorecard: Map<String, Any?>? = null,
    val scores: ScoresShape? = null,
    val company_intel: Map<String, Any?>? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class JdQualityShape(
    val score: Double? = null,
    val level: String? = null,
    val warnings: List<String>? = null,
)

@JsonClass(generateAdapter = true)
data class ConfirmedFacts(
    val full_name: String? = null,
    val email: String? = null,
    val current_title: String? = null,
    val years_experience: Int? = null,
    val location: String? = null,
)

@JsonClass(generateAdapter = true)
data class ModuleStatusEntry(
    val state: String? = null,
    val message: String? = null,
    val updatedAt: Long? = null,
)

@JsonClass(generateAdapter = true)
data class ScoresShape(
    val overall: Double? = null,
    val keyword: Double? = null,
    val readability: Double? = null,
    val structure: Double? = null,
    val ats: Double? = null,
    val topFix: String? = null,
)

/* ============================================================
 * Generation jobs
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class CreateGenerationJobRequest(
    val application_id: String,
    val requested_modules: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class GenerationJob(
    val id: String,
    val user_id: String? = null,
    val application_id: String? = null,
    val status: String? = null,
    val progress: Int? = null,
    val phase: String? = null,
    val message: String? = null,
    val current_agent: String? = null,
    val completed_steps: List<String>? = null,
    val total_steps: Int? = null,
    val requested_modules: List<String>? = null,
    val generation_plan: Map<String, Any?>? = null,
    val result: Map<String, Any?>? = null,
    val error: Map<String, Any?>? = null,
    val started_at: String? = null,
    val finished_at: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class GenerationJobEvent(
    val id: String? = null,
    val job_id: String? = null,
    val sequence_no: Int? = null,
    val event_name: String? = null,
    val agent_name: String? = null,
    val stage: String? = null,
    val status: String? = null,
    val message: String? = null,
    val payload: Map<String, Any?>? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class CreateApplicationRequest(
    val title: String,
    val job_title: String? = null,
    val company: String? = null,
    val location: String? = null,
    val jd_text: String? = null,
)

/* ============================================================
 * Resume parse
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class ResumeParseResponse(
    val text: String? = null,
    val fileName: String? = null,
    val contentType: String? = null,
)

/* ============================================================
 * Evidence
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class EvidenceItem(
    val id: String,
    val user_id: String? = null,
    val application_id: String? = null,
    val title: String? = null,
    val description: String? = null,
    val type: String? = null,
    val url: String? = null,
    val storage_url: String? = null,
    val file_url: String? = null,
    val file_name: String? = null,
    val skills: List<String>? = null,
    val tools: List<String>? = null,
    val tags: List<String>? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

/* ============================================================
 * Gaps (gap reports + items)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class GapAnalyzeRequest(
    val application_id: String,
    val refresh: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class GapReport(
    val id: String,
    val application_id: String? = null,
    val user_id: String? = null,
    val overall_match: Double? = null,
    val skill_match: Double? = null,
    val experience_match: Double? = null,
    val gap_count: Int? = null,
    val critical_count: Int? = null,
    val items: List<GapItem>? = null,
    val summary: String? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class GapItem(
    val id: String? = null,
    val skill: String? = null,
    val area: String? = null,
    val severity: String? = null,
    val recommendation: String? = null,
    val effort: String? = null,
    val priority: Int? = null,
)

/* ============================================================
 * Skills + dev goals (/development)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class UserSkill(
    val id: String,
    val skill_id: String? = null,
    val name: String? = null,
    val category: String? = null,
    val level: String? = null,
    val proficiency: Int? = null,
    val years_experience: Double? = null,
    val verified: Boolean? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class CreateUserSkillRequest(
    val name: String,
    val category: String? = null,
    val level: String? = null,
    val years_experience: Double? = null,
)

@JsonClass(generateAdapter = true)
data class DevGoal(
    val id: String,
    val title: String? = null,
    val description: String? = null,
    val skill: String? = null,
    val target_date: String? = null,
    val status: String? = null,
    val progress_pct: Int? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class CreateDevGoalRequest(
    val title: String,
    val skill: String? = null,
    val description: String? = null,
    val target_date: String? = null,
)

@JsonClass(generateAdapter = true)
data class DevSummary(
    val skills_count: Int = 0,
    val active_goals: Int = 0,
    val gaps_open: Int = 0,
    val mastery_score: Double? = null,
)

/* ============================================================
 * Benchmark (ideal candidate profile)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class GenerateBenchmarkRequest(
    val job_id: String? = null,
    val jd_text: String? = null,
    val job_title: String? = null,
    val company: String? = null,
)

@JsonClass(generateAdapter = true)
data class BenchmarkDoc(
    val id: String,
    val user_id: String? = null,
    val job_id: String? = null,
    val job_title: String? = null,
    val company: String? = null,
    val ideal_profile: Map<String, Any?>? = null,
    val required_skills: List<String>? = null,
    val nice_to_have: List<String>? = null,
    val years_experience: String? = null,
    val score: Double? = null,
    val created_at: String? = null,
)

/* ============================================================
 * Builder (single-doc generator)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class BuilderGenerateRequest(
    val doc_type: String,                  // "cv" | "cover_letter" | "personal_statement" | "portfolio"
    val job_id: String? = null,
    val profile_id: String? = null,
    val jd_text: String? = null,
    val tone: String? = null,
    val length: String? = null,
)

@JsonClass(generateAdapter = true)
data class BuilderDocument(
    val id: String,
    val doc_type: String? = null,
    val title: String? = null,
    val html_content: String? = null,
    val plain_text: String? = null,
    val word_count: Int? = null,
    val version: Int? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
)

/* ============================================================
 * Consultant (career roadmaps + chat coaching)
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class RoadmapRequest(
    val target_role: String,
    val target_company: String? = null,
    val timeframe_months: Int? = null,
    val current_level: String? = null,
)

@JsonClass(generateAdapter = true)
data class CareerRoadmap(
    val id: String,
    val target_role: String? = null,
    val target_company: String? = null,
    val timeframe_months: Int? = null,
    val current_level: String? = null,
    val phases: List<RoadmapPhase>? = null,
    val progress_pct: Int? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class RoadmapPhase(
    val id: String? = null,
    val title: String? = null,
    val description: String? = null,
    val milestones: List<String>? = null,
    val skills: List<String>? = null,
    val duration_weeks: Int? = null,
    val completed: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class CoachRequest(
    val message: String,
    val context: Map<String, Any?>? = null,
    val history: List<CoachTurn>? = null,
)

@JsonClass(generateAdapter = true)
data class CoachTurn(
    val role: String,        // "user" | "assistant"
    val content: String,
)

@JsonClass(generateAdapter = true)
data class CoachResponse(
    val reply: String? = null,
    val suggestions: List<String>? = null,
    val resources: List<String>? = null,
)

/* ============================================================
 * Export
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class ExportRequest(
    val application_id: String,
    val doc_type: String,
    val format: String = "pdf",   // "pdf" | "docx"
)

@JsonClass(generateAdapter = true)
data class ExportRecord(
    val id: String,
    val user_id: String? = null,
    val application_id: String? = null,
    val doc_type: String? = null,
    val format: String? = null,
    val file_url: String? = null,
    val file_size: Long? = null,
    val download_url: String? = null,
    val created_at: String? = null,
)

/* ============================================================
 * Orgs / members / API keys / billing / audit
 * ============================================================ */

@JsonClass(generateAdapter = true)
data class Organization(
    val id: String,
    val name: String? = null,
    val plan: String? = null,
    val role: String? = null,
    val member_count: Int? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class OrgMember(
    val id: String? = null,
    val user_id: String? = null,
    val email: String? = null,
    val full_name: String? = null,
    val role: String? = null,
    val joined_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class ApiKey(
    val id: String,
    val name: String? = null,
    val prefix: String? = null,
    val last_used_at: String? = null,
    val created_at: String? = null,
    val revoked_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class CreateApiKeyRequest(
    val name: String,
)

@JsonClass(generateAdapter = true)
data class CreateApiKeyResponse(
    val id: String,
    val key: String,           // shown once
    val name: String? = null,
    val created_at: String? = null,
)

@JsonClass(generateAdapter = true)
data class BillingStatus(
    val plan: String? = null,                 // "free" | "pro" | "team"
    val status: String? = null,               // "active" | "trialing" | "past_due"
    val period_end: String? = null,
    val seats: Int? = null,
    val seats_used: Int? = null,
    val applications_used: Int? = null,
    val applications_limit: Int? = null,
    val exports_used: Int? = null,
    val exports_limit: Int? = null,
    val testing_mode: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class BillingPortalResponse(
    val url: String? = null,
)

@JsonClass(generateAdapter = true)
data class AuditEvent(
    val id: String? = null,
    val event: String? = null,
    val actor: String? = null,
    val target: String? = null,
    val metadata: Map<String, Any?>? = null,
    val created_at: String? = null,
)
