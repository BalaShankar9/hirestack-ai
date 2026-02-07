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
  scorecard?: Scorecard;

  /** Document version histories */
  cvVersions?: DocVersion[];
  clVersions?: DocVersion[];

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
