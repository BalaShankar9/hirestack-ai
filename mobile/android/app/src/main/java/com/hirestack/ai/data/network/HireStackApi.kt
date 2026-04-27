package com.hirestack.ai.data.network

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
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

    @DELETE("candidates/{id}")
    suspend fun deleteCandidate(@Path("id") id: String)

    @POST("candidates/{id}/move")
    suspend fun moveCandidateStage(@Path("id") id: String, @Body body: Map<String, String>): Candidate

    // Interview Coach
    @GET("interview/sessions")
    suspend fun listInterviewSessions(): List<InterviewSession>

    @GET("interview/sessions/{id}")
    suspend fun getInterviewSession(@Path("id") id: String): InterviewSession

    @DELETE("interview/sessions/{id}")
    suspend fun deleteInterviewSession(@Path("id") id: String)

    // Career analytics
    @GET("career/portfolio")
    suspend fun careerPortfolio(): CareerPortfolio

    @GET("career/timeline")
    suspend fun careerTimeline(@Query("days") days: Int = 90): List<CareerSnapshot>

    @GET("career/outcomes/funnel")
    suspend fun careerFunnel(): ConversionFunnel

    // Learning
    @GET("learning/streak")
    suspend fun learningStreak(): LearningStreak

    @GET("learning/today")
    suspend fun learningToday(): List<LearningChallenge>

    @GET("learning/history")
    suspend fun learningHistory(@Query("limit") limit: Int = 50): List<LearningChallenge>

    // Salary
    @GET("salary/")
    suspend fun listSalaryAnalyses(): List<SalaryAnalysis>

    @GET("salary/{id}")
    suspend fun getSalaryAnalysis(@Path("id") id: String): SalaryAnalysis

    // Variants (A/B Doc Lab)
    @GET("variants/")
    suspend fun listVariants(
        @Query("application_id") applicationId: String? = null,
        @Query("document_type") documentType: String? = null,
    ): List<DocVariant>

    @PUT("variants/{id}/select")
    suspend fun selectVariant(@Path("id") id: String): SelectVariantResponse

    // Knowledge library
    @GET("knowledge/resources")
    suspend fun listKnowledgeResources(
        @Query("category") category: String? = null,
        @Query("type") type: String? = null,
        @Query("difficulty") difficulty: String? = null,
        @Query("search") search: String? = null,
        @Query("featured") featured: Boolean = false,
        @Query("limit") limit: Int = 50,
    ): List<KnowledgeResource>

    @GET("knowledge/progress")
    suspend fun knowledgeProgress(): List<KnowledgeProgress>

    @GET("knowledge/recommendations")
    suspend fun knowledgeRecommendations(): List<KnowledgeRecommendation>

    @POST("knowledge/recommendations/{id}/dismiss")
    suspend fun dismissKnowledgeRecommendation(@Path("id") id: String)

    // ---- Tier 9 (parity pass) ----

    // Resume parsing
    @Multipart
    @POST("resume/parse")
    suspend fun parseResume(@Part file: MultipartBody.Part): ResumeParseResponse

    // Generation jobs
    @POST("generate/jobs")
    suspend fun createGenerationJob(@Body body: CreateGenerationJobRequest): GenerationJob

    @GET("generate/jobs/{id}/status")
    suspend fun getGenerationJob(@Path("id") id: String): GenerationJob

    @POST("generate/jobs/{id}/cancel")
    suspend fun cancelGenerationJob(@Path("id") id: String)

    @POST("generate/jobs/{id}/retry")
    suspend fun retryGenerationJob(@Path("id") id: String): GenerationJob

    // Gaps
    @POST("gaps/analyze")
    suspend fun analyzeGaps(@Body body: GapAnalyzeRequest): GapReport

    @GET("gaps")
    suspend fun listGapReports(): List<GapReport>

    @GET("gaps/{id}")
    suspend fun getGapReport(@Path("id") id: String): GapReport

    // Skills + dev goals
    @GET("development/skills")
    suspend fun listUserSkills(): List<UserSkill>

    @POST("development/skills")
    suspend fun addUserSkill(@Body body: CreateUserSkillRequest): UserSkill

    @DELETE("development/skills/{id}")
    suspend fun removeUserSkill(@Path("id") id: String)

    @GET("development/goals")
    suspend fun listGoals(): List<DevGoal>

    @POST("development/goals")
    suspend fun createGoal(@Body body: CreateDevGoalRequest): DevGoal

    @PATCH("development/goals/{id}")
    suspend fun updateGoal(@Path("id") id: String, @Body body: Map<String, Any?>): DevGoal

    @DELETE("development/goals/{id}")
    suspend fun deleteGoal(@Path("id") id: String)

    @GET("development/summary")
    suspend fun developmentSummary(): DevSummary

    // Benchmark
    @POST("benchmark/generate")
    suspend fun generateBenchmark(@Body body: GenerateBenchmarkRequest): BenchmarkDoc

    @GET("benchmark/{id}")
    suspend fun getBenchmark(@Path("id") id: String): BenchmarkDoc

    // Builder
    @POST("builder/generate")
    suspend fun builderGenerate(@Body body: BuilderGenerateRequest): BuilderDocument

    @GET("builder/documents")
    suspend fun listBuilderDocuments(): List<BuilderDocument>

    @GET("builder/documents/{id}")
    suspend fun getBuilderDocument(@Path("id") id: String): BuilderDocument

    @DELETE("builder/documents/{id}")
    suspend fun deleteBuilderDocument(@Path("id") id: String)

    // Consultant
    @POST("consultant/roadmap")
    suspend fun createRoadmap(@Body body: RoadmapRequest): CareerRoadmap

    @GET("consultant/roadmaps")
    suspend fun listRoadmaps(): List<CareerRoadmap>

    @GET("consultant/roadmap/{id}")
    suspend fun getRoadmap(@Path("id") id: String): CareerRoadmap

    @POST("consultant/coach")
    suspend fun coach(@Body body: CoachRequest): CoachResponse

    // Export
    @POST("export")
    suspend fun createExport(@Body body: ExportRequest): ExportRecord

    @GET("export")
    suspend fun listExports(@Query("limit") limit: Int = 50): List<ExportRecord>

    @GET("export/{id}")
    suspend fun getExport(@Path("id") id: String): ExportRecord

    // Orgs / members
    @GET("orgs")
    suspend fun listOrgs(): List<Organization>

    @GET("orgs/{id}/members")
    suspend fun listOrgMembers(@Path("id") id: String): List<OrgMember>

    @GET("orgs/{id}/audit")
    suspend fun listOrgAudit(@Path("id") id: String, @Query("limit") limit: Int = 50): List<AuditEvent>

    // API keys
    @GET("api-keys")
    suspend fun listApiKeys(): List<ApiKey>

    @POST("api-keys")
    suspend fun createApiKey(@Body body: CreateApiKeyRequest): CreateApiKeyResponse

    @DELETE("api-keys/{id}")
    suspend fun revokeApiKey(@Path("id") id: String)

    // Billing
    @GET("billing/status")
    suspend fun billingStatus(): BillingStatus

    @POST("billing/portal")
    suspend fun billingPortal(): BillingPortalResponse
}
