/**
 * Data models — TypeScript types for Supabase tables.
 *
 * These mirror the DB schema and are used across the frontend.
 * Import path stays `@/lib/firestore/models` for backward compat.
 */

/* ------------------------------------------------------------------ */
/*  Primitives                                                         */
/* ------------------------------------------------------------------ */

export type ModuleKey =
  | "benchmark"
  | "gaps"
  | "learningPlan"
  | "cv"
  | "coverLetter"
  | "personalStatement"
  | "portfolio"
  | "scorecard";

export type ModuleStatusState = "idle" | "queued" | "generating" | "ready" | "error";

export interface ModuleStatus {
  state: ModuleStatusState;
  progress?: number;
  error?: string;
  updatedAt?: number;
}

/** @deprecated use ModuleStatus */
export type ModuleState = ModuleStatus;

/* ------------------------------------------------------------------ */
/*  JD / Resume types                                                  */
/* ------------------------------------------------------------------ */

export interface JDQuality {
  score: number;
  flags: string[];
  summary: string;
}

export interface ResumeArtifact {
  /** URL in Supabase Storage */
  url?: string;
  /** Extracted plain text */
  text?: string;
  name?: string;
  size?: number;
  type?: string;
}

export interface ConfirmedFacts {
  jobTitle: string;
  company?: string;
  jdText: string;
  jdQuality: JDQuality;
  resume: ResumeArtifact;
}

/* ------------------------------------------------------------------ */
/*  Module payloads                                                     */
/* ------------------------------------------------------------------ */

export interface BenchmarkModule {
  /** Overall summary of the ideal candidate */
  summary?: string;
  /** Rubric lines */
  rubric: string[];
  /** Target keywords for the role */
  keywords: string[];
  /** Optional structured dimensions */
  dimensions?: BenchmarkDimension[];
  overallScore?: number;
  /** Full HTML CV of the ideal benchmark candidate */
  benchmarkCvHtml?: string;
  /** Ideal candidate profile */
  idealProfile?: {
    title?: string;
    name?: string;
    years_experience?: number;
    [key: string]: any;
  };
  /** Ideal candidate skills */
  idealSkills?: string[];
  createdAt?: number;
}

export interface BenchmarkDimension {
  name: string;
  weight: number;
  score: number;
  evidence: string[];
  keywords: string[];
}

export interface GapsModule {
  /** Keywords the candidate is missing */
  missingKeywords: string[];
  /** Keywords the candidate already covers */
  strengths: string[];
  /** Actionable recommendations */
  recommendations: string[];
  /** Optional structured gaps */
  gaps?: GapItem[];
  summary?: string;
  /** Role compatibility percentage */
  compatibility?: number;
  createdAt?: number;
}

export interface GapItem {
  dimension: string;
  gap: string;
  severity: "low" | "medium" | "high" | "critical";
  suggestion: string;
}

export interface LearningPlanModule {
  /** Focus areas */
  focus: string[];
  /** Week-by-week plan */
  plan: LearningWeek[];
  /** Recommended resources */
  resources: LearningResource[];
  summary?: string;
  createdAt?: number;
}

export interface LearningWeek {
  week: number;
  theme: string;
  outcomes: string[];
  tasks: string[];
}

export interface LearningResource {
  title: string;
  provider?: string;
  timebox?: string;
  skill?: string;
  url?: string;
}

export interface LearningItem {
  title: string;
  type: "course" | "project" | "cert" | "practice" | "reading";
  effort: string;
  url?: string;
  priority: "low" | "medium" | "high";
}

export interface Scorecard {
  overall: number;
  dimensions: ScorecardDimension[];
  summary?: string;
  match?: number;
  atsReadiness?: number;
  recruiterScan?: number;
  evidenceStrength?: number;
  topFix?: string;
  updatedAt?: number;
}

export interface ScorecardDimension {
  name: string;
  score: number;
  feedback: string;
}

export interface DocVersion {
  id: string;
  html: string;
  label?: string;
  createdAt: number;
}

/* ------------------------------------------------------------------ */
/*  Application document                                               */
/* ------------------------------------------------------------------ */

export interface ApplicationDoc {
  id: string;
  userId: string;
  title: string;
  status: "draft" | "active" | "archived";
  createdAt: number;
  updatedAt: number;

  /** Step-1 confirmed facts */
  confirmedFacts?: ConfirmedFacts;

  /** Whether user has locked/confirmed facts */
  factsLocked?: boolean;

  /** Module statuses */
  modules: Record<ModuleKey, ModuleState>;

  /** Module outputs */
  benchmark?: BenchmarkModule;
  gaps?: GapsModule;
  learningPlan?: LearningPlanModule;
  cvHtml?: string;
  coverLetterHtml?: string;
  personalStatementHtml?: string;
  portfolioHtml?: string;
  resumeHtml?: string;
  scorecard?: Scorecard;

  /** Document version histories */
  cvVersions?: DocVersion[];
  clVersions?: DocVersion[];
  psVersions?: DocVersion[];
  portfolioVersions?: DocVersion[];

  /** AI validation results */
  validation?: Record<string, any>;

  /** Adaptive document engine outputs */
  discoveredDocuments?: Array<{ key: string; label: string; priority: string; reason?: string }>;
  generatedDocuments?: Record<string, string>;
  benchmarkDocuments?: Record<string, string>;
  documentStrategy?: string;
  /** Company intelligence gathered during recon */
  companyIntel?: Record<string, any>;

  /** Scores snapshot for list views */
  scores?: {
    match?: number;
    atsReadiness?: number;
    recruiterScan?: number;
    evidenceStrength?: number;
    topFix?: string;
    benchmark?: number;
    gaps?: number;
    cv?: number;
    coverLetter?: number;
    overall?: number;
  };

}

/* ------------------------------------------------------------------ */
/*  Evidence document                                                   */
/* ------------------------------------------------------------------ */

export interface EvidenceDoc {
  id: string;
  userId: string;
  applicationId: string | null;
  kind: "link" | "file";
  type: "cert" | "project" | "course" | "award" | "publication" | "other";
  title: string;
  description?: string;
  url?: string;
  storageUrl?: string;
  fileUrl?: string;
  fileName?: string;
  skills: string[];
  tools: string[];
  tags: string[];
  createdAt: number;
  updatedAt: number;
}

/* ------------------------------------------------------------------ */
/*  Task document                                                       */
/* ------------------------------------------------------------------ */

export interface TaskDoc {
  id: string;
  userId: string;
  applicationId: string | null;
  /** Alias for applicationId — used by existing components */
  appId?: string | null;
  source: "benchmark" | "gaps" | "learningPlan" | "coach" | "manual";
  title: string;
  description?: string;
  /** Short detail text displayed under the title */
  detail?: string;
  /** Explanation of why the task matters */
  why?: string;
  status: "todo" | "in-progress" | "done" | "skipped";
  priority: "low" | "medium" | "high";
  dueDate?: number;
  createdAt: number;
  updatedAt: number;
}

/* ------------------------------------------------------------------ */
/*  Event / analytics document                                          */
/* ------------------------------------------------------------------ */

export interface EventDoc {
  id: string;
  userId: string;
  applicationId?: string;
  event: string;
  payload?: Record<string, any>;
  createdAt: number;
}

export type GenerationJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface GenerationJobDoc {
  id: string;
  userId: string;
  applicationId: string;
  requestedModules: string[];
  status: GenerationJobStatus;
  progress: number;
  phase?: string;
  message?: string;
  cancelRequested: boolean;
  currentAgent?: string;
  completedSteps: number;
  totalSteps: number;
  activeSourcesCount: number;
  result?: Record<string, any>;
  errorMessage?: string;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  updatedAt: number;
}

export interface GenerationJobEventDoc {
  id: string;
  jobId: string;
  userId: string;
  applicationId: string;
  sequenceNo: number;
  eventName: string;
  agentName?: string;
  stage?: string;
  status?: string;
  message: string;
  source?: string;
  url?: string;
  latencyMs?: number;
  payload?: Record<string, any>;
  createdAt: number;
}

/* ------------------------------------------------------------------ */
/*  Runtime truth types (v7 — mission-control parity)                  */
/* ------------------------------------------------------------------ */

/** Optimizer final analysis report from the agent pipeline. */
export interface FinalAnalysisReport {
  initial_ats_score: number;
  final_ats_score: number;
  keyword_gap_delta: number;
  readability_delta: number;
  residual_issue_count: number;
  missing_keywords?: string[];
  suggestions?: string[];
}

/** Compact evidence summary from pipeline execution. */
export interface EvidenceSummary {
  evidence_count: number;
  tier_distribution: Record<string, number>;
  citation_count: number;
  fabricated_count: number;
  unlinked_count: number;
}

/** A single claim→evidence citation from the fact-checker. */
export interface ClaimCitation {
  claim_text: string;
  evidence_ids: string[];
  classification: "verified" | "supported" | "inferred" | "embellished" | "fabricated" | "unsupported";
  confidence: number;
  tier?: string;
}

/** Per-stage checkpoint from the durable workflow runtime. */
export interface WorkflowStageState {
  status: "pending" | "running" | "completed" | "failed" | "skipped" | "timed_out";
  latency_ms?: number;
}

/** Workflow state snapshot from the pipeline execution. */
export interface WorkflowState {
  stages: Record<string, WorkflowStageState>;
}

/** Validation report from the schema validator. */
export interface ValidationReport {
  valid: boolean;
  checks: Record<string, boolean>;
  issues: Array<{ field: string; severity: string; message: string }>;
  hard_failures: number;
  soft_warnings: number;
  confidence: number;
}

/** Residual risk summary derived from final analysis + validation. */
export interface ResidualRiskSummary {
  evidenceStrength: number;
  contradictionCount: number;
  unsupportedClaims: number;
  residualATSGap: number;
  confidence: number;
}

/** Replay report from the replay engine. */
export interface ReplayReport {
  job_id: string;
  pipeline_name: string;
  job_status: string;
  completed_stages: string[];
  failed_stages: string[];
  skipped_stages: string[];
  timed_out_stages: string[];
  artifacts_present: string[];
  artifacts_missing: string[];
  evidence_count: number;
  evidence_tier_distribution: Record<string, number>;
  citation_count: number;
  unlinked_citation_count: number;
  fabricated_claim_count: number;
  failure_class: string;
  likely_root_cause: string;
  suggested_regression_target?: string;
  event_count: number;
  /** Computed on the frontend: true when job_status is "failed" or failure_class is not "unknown". */
  is_failure?: boolean;
}

/** Extended pipeline meta returned from generation endpoints. */
export interface PipelineMeta {
  quality_scores?: Record<string, Record<string, number>>;
  fact_check?: Record<string, any>;
  agent_powered?: boolean;
  final_analysis?: FinalAnalysisReport | null;
  validation_report?: ValidationReport | null;
  citations?: ClaimCitation[] | null;
  evidence_summary?: EvidenceSummary | null;
  workflow_state?: WorkflowState | null;
  company_intel?: Record<string, any>;
}

/* ------------------------------------------------------------------ */
/*  Document Library types                                              */
/* ------------------------------------------------------------------ */

export type DocumentCategory = "benchmark" | "fixed" | "tailored";
export type DocumentStatus = "planned" | "generating" | "ready" | "error";
export type DocumentSource = "planner" | "user_request" | "auto_evolve" | "migration";

export interface DocumentLibraryItem {
  id: string;
  userId: string;
  applicationId?: string | null;
  docType: string;
  docCategory: DocumentCategory;
  label: string;
  htmlContent: string;
  metadata: Record<string, any>;
  version: number;
  status: DocumentStatus;
  errorMessage?: string;
  source: DocumentSource;
  createdAt: number;
  updatedAt: number;
}

export interface DocumentLibrarySummary {
  benchmark: { total: number; ready: number; generating: number; planned: number; error: number };
  fixed: { total: number; ready: number; generating: number; planned: number; error: number };
  tailored: { total: number; ready: number; generating: number; planned: number; error: number };
}

/* ------------------------------------------------------------------ */
/*  Knowledge Library types                                            */
/* ------------------------------------------------------------------ */

export type ResourceCategory =
  | "resume_writing"
  | "interview_prep"
  | "salary_negotiation"
  | "career_strategy"
  | "career_development"
  | "networking"
  | "industry_knowledge"
  | "soft_skills"
  | "technical_skills"
  | "job_search"
  | "personal_branding"
  | "skill_development"
  | "general";

export type ResourceType =
  | "guide" | "template" | "book" | "video" | "course" | "article"
  | "tool" | "checklist" | "cheatsheet" | "reference" | "tutorial" | "podcast";
export type ResourceDifficulty = "beginner" | "intermediate" | "advanced";

export interface KnowledgeResource {
  id: string;
  title: string;
  description: string;
  category: ResourceCategory;
  resource_type: ResourceType;
  difficulty: ResourceDifficulty;
  url?: string | null;
  content_html?: string | null;
  cover_image_url?: string | null;
  provider?: string | null;
  estimated_time?: string | null;
  skills: string[];
  tags?: string[];
  is_featured: boolean;
  is_published?: boolean;
  sort_order?: number;
  created_at: string;
  updated_at?: string;
}

export type ProgressStatus = "saved" | "in_progress" | "completed";

export interface UserKnowledgeProgress {
  id: string;
  user_id: string;
  resource_id: string;
  status: ProgressStatus;
  progress_pct: number;
  rating?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

/* ------------------------------------------------------------------ */
/*  Global Skills & Development types                                  */
/* ------------------------------------------------------------------ */

export type SkillCategory =
  | "technical"
  | "soft_skill"
  | "tool"
  | "language"
  | "framework"
  | "methodology"
  | "certification"
  | "domain"
  | "other";

export type Proficiency = "beginner" | "intermediate" | "advanced" | "expert";

export interface UserSkill {
  id: string;
  user_id: string;
  skill_name: string;
  category: SkillCategory;
  proficiency: Proficiency;
  years_experience?: number | null;
  source: string;
  created_at: string;
  updated_at: string;
}

export type GapStatus = "open" | "in_progress" | "closed" | "dismissed";
export type GapSeverity = "critical" | "high" | "medium" | "low";

export interface UserSkillGap {
  id: string;
  user_id: string;
  skill_name: string;
  gap_severity: GapSeverity;
  current_level?: string | null;
  target_level?: string | null;
  frequency: number;
  application_ids: string[];
  priority_score: number;
  status: GapStatus;
  created_at: string;
  updated_at: string;
}

export type GoalStatus = "active" | "completed" | "paused" | "archived";
export type GoalType =
  | "skill_acquisition"
  | "certification"
  | "career_transition"
  | "promotion_readiness"
  | "industry_knowledge"
  | "general";

export interface UserLearningGoal {
  id: string;
  user_id: string;
  title: string;
  description?: string | null;
  target_skills: string[];
  goal_type: GoalType;
  status: GoalStatus;
  target_date?: string | null;
  progress_pct: number;
  created_at: string;
  updated_at: string;
}

export interface ResourceRecommendation {
  id: string;
  user_id: string;
  resource_id: string;
  reason: string;
  relevance_score: number;
  source_gap_id?: string | null;
  source_goal_id?: string | null;
  status: "pending" | "viewed" | "dismissed";
  created_at: string;
}

export interface SkillsProfileSummary {
  total_skills: number;
  skills_by_category: Record<string, number>;
  open_gaps: number;
  critical_gaps: number;
  high_gaps: number;
  top_gaps: UserSkillGap[];
  active_goals: number;
  goals: UserLearningGoal[];
}
