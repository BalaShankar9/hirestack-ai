import type { Bytes } from "firebase/firestore";

export type AppStatus = "draft" | "generating" | "active" | "archived";

export type ModuleKey =
  | "benchmark"
  | "gaps"
  | "learningPlan"
  | "cv"
  | "coverLetter"
  | "export";

export type ModuleState = "idle" | "queued" | "generating" | "ready" | "error";

export type TaskStatus = "todo" | "done";
export type TaskPriority = "low" | "medium" | "high";
export type TaskSource = "gaps" | "learningPlan" | "coach" | "manual";

export type EvidenceKind = "link" | "file";

export type CoachActionKind = "fix" | "write" | "collect" | "review";

export interface ModuleStatus {
  state: ModuleState;
  progress: number; // 0..100
  updatedAt: number; // epoch ms
  error?: string;
}

export interface Scorecard {
  match: number; // 0..100
  atsReadiness: number; // 0..100
  recruiterScan: number; // 0..100
  evidenceStrength: number; // 0..100
  topFix: string;
  updatedAt: number; // epoch ms
}

export interface ConfirmedFacts {
  fullName?: string;
  email?: string;
  location?: string;
  headline?: string;
  yearsExperience?: number;
  skills: string[];
  highlights: string[]; // bullet-style facts
}

export interface JDQuality {
  score: number; // 0..100
  issues: string[];
  suggestions: string[];
}

export interface ApplicationJob {
  title: string;
  company?: string;
  description: string;
  quality: JDQuality;
}

export interface ResumeArtifact {
  fileName?: string;
  storagePath?: string;
  storageUrl?: string;
  extractedText?: string;
  inlineBytes?: Bytes;
  inlineMimeType?: string;
  inlineSize?: number;
}

export interface BenchmarkModule {
  summary: string;
  keywords: string[];
  rubric: string[];
  createdAt: number;
}

export interface GapsModule {
  missingKeywords: string[];
  strengths: string[];
  recommendations: string[];
  createdAt: number;
}

export interface LearningResource {
  title: string;
  url?: string;
  provider?: string;
  timebox?: string;
  skill?: string;
}

export interface LearningPlanModule {
  focus: string[];
  plan: Array<{
    week: number;
    theme: string;
    outcomes: string[];
    tasks: string[];
  }>;
  resources: LearningResource[];
  createdAt: number;
}

export interface DocVersion {
  id: string;
  label: string;
  createdAt: number;
  contentHtml: string;
}

export interface DocModule {
  contentHtml: string;
  versions: DocVersion[];
  updatedAt: number;
}

export interface EvidenceDoc {
  id: string;
  userId: string;
  kind: EvidenceKind;
  title: string;
  description?: string;
  url?: string;
  storagePath?: string;
  storageUrl?: string;
  mimeType?: string;
  tags: string[];
  skills: string[];
  tools: string[];
  createdAt: number;
  updatedAt: number;
}

export interface TaskDoc {
  id: string;
  userId: string;
  appId?: string;
  source: TaskSource;
  module?: ModuleKey;
  title: string;
  detail?: string;
  why?: string;
  priority: TaskPriority;
  status: TaskStatus;
  createdAt: number;
  completedAt?: number;
  tags: string[];
}

export interface AnalyticsEventDoc {
  id: string;
  userId: string;
  name:
    | "view_workspace"
    | "generate_clicked"
    | "export_clicked"
    | "task_completed";
  appId?: string;
  properties?: Record<string, unknown>;
  createdAt: number;
}

export interface ApplicationDoc {
  id: string;
  userId: string;
  createdAt: number;
  updatedAt: number;
  status: AppStatus;

  job: ApplicationJob;
  resume: ResumeArtifact;

  factsLocked: boolean;
  confirmedFacts: ConfirmedFacts | null;

  modules: Record<ModuleKey, ModuleStatus>;
  scores: Scorecard;

  benchmark?: BenchmarkModule;
  gaps?: GapsModule;
  learningPlan?: LearningPlanModule;

  docs: {
    baseResumeHtml?: string;
    cv: DocModule;
    coverLetter: DocModule;
  };
}
