/**
 * Firestore Operations — Supabase implementation.
 *
 * All CRUD operations and utility/builder functions for the frontend data layer.
 * Import path stays `@/lib/firestore/ops` for backward compat.
 */

import { supabase } from "@/lib/supabase";
import { TABLES } from "./paths";
import type {
  ApplicationDoc,
  BenchmarkModule,
  BenchmarkDimension,
  ConfirmedFacts,
  DocVersion,
  EvidenceDoc,
  GapsModule,
  GapItem,
  JDQuality,
  LearningPlanModule,
  LearningItem,
  ModuleKey,
  ModuleStatus,
  ModuleStatusState,
  Scorecard,
  ScorecardDimension,
  TaskDoc,
  EventDoc,
} from "./models";

/* ================================================================== */
/*  ROW MAPPERS — convert DB snake_case to frontend camelCase          */
/* ================================================================== */

const ts = (v: any): number => {
  if (!v) return Date.now();
  if (typeof v === "number") return v;
  return new Date(v).getTime();
};

const DEFAULT_MODULES: Record<ModuleKey, ModuleStatus> = {
  benchmark: { state: "idle" },
  gaps: { state: "idle" },
  learningPlan: { state: "idle" },
  cv: { state: "idle" },
  coverLetter: { state: "idle" },
  scorecard: { state: "idle" },
};

export function mapApplicationRow(row: any): ApplicationDoc {
  return {
    id: row.id,
    userId: row.user_id,
    title: row.title ?? "",
    status: row.status ?? "draft",
    createdAt: ts(row.created_at),
    updatedAt: ts(row.updated_at),
    confirmedFacts: row.confirmed_facts ?? undefined,
    factsLocked: row.facts_locked ?? false,
    modules: row.modules ?? { ...DEFAULT_MODULES },
    benchmark: row.benchmark ?? undefined,
    gaps: row.gaps ?? undefined,
    learningPlan: row.learning_plan ?? undefined,
    cvHtml: row.cv_html ?? undefined,
    coverLetterHtml: row.cover_letter_html ?? undefined,
    scorecard: row.scorecard ?? undefined,
    scores: row.scores ?? undefined,
    cvVersions: row.cv_versions ?? [],
    clVersions: row.cl_versions ?? [],
  };
}

export function mapEvidenceRow(row: any): EvidenceDoc {
  return {
    id: row.id,
    userId: row.user_id,
    applicationId: row.application_id ?? null,
    kind: row.kind ?? (row.file_url ? "file" : "link"),
    type: row.type ?? "other",
    title: row.title ?? "",
    description: row.description ?? undefined,
    url: row.url ?? undefined,
    storageUrl: row.storage_url ?? row.file_url ?? undefined,
    fileUrl: row.file_url ?? undefined,
    fileName: row.file_name ?? undefined,
    skills: row.skills ?? [],
    tools: row.tools ?? [],
    tags: row.tags ?? [],
    createdAt: ts(row.created_at),
    updatedAt: ts(row.updated_at),
  };
}

export function mapTaskRow(row: any): TaskDoc {
  return {
    id: row.id,
    userId: row.user_id,
    applicationId: row.application_id ?? null,
    appId: row.application_id ?? null,
    source: row.source ?? "manual",
    title: row.title ?? "",
    description: row.description ?? undefined,
    status: row.status ?? "todo",
    priority: row.priority ?? "medium",
    dueDate: row.due_date ? ts(row.due_date) : undefined,
    createdAt: ts(row.created_at),
    updatedAt: ts(row.updated_at),
  };
}

/* ================================================================== */
/*  ID GENERATOR                                                        */
/* ================================================================== */

export function uid(prefix = "id"): string {
  const rand = Math.random().toString(36).slice(2, 10);
  const time = Date.now().toString(36);
  return `${prefix}_${time}${rand}`;
}

/* ================================================================== */
/*  APPLICATION CRUD                                                    */
/* ================================================================== */

export async function createApplication(
  userId: string,
  title: string,
  confirmedFacts?: ConfirmedFacts
): Promise<string> {
  const row = {
    user_id: userId,
    title,
    status: "draft",
    confirmed_facts: confirmedFacts ?? null,
    modules: { ...DEFAULT_MODULES },
    scores: null,
  };

  const { data, error } = await supabase.from(TABLES.applications).insert(row).select("id").single();
  if (error) throw error;
  return data.id;
}

export async function getApplication(appId: string): Promise<ApplicationDoc | null> {
  const { data, error } = await supabase
    .from(TABLES.applications)
    .select("*")
    .eq("id", appId)
    .maybeSingle();

  if (error) throw error;
  return data ? mapApplicationRow(data) : null;
}

export async function patchApplication(
  appId: string,
  patch: Record<string, any>
): Promise<void> {
  // Convert camelCase keys to snake_case for DB columns
  const dbPatch: Record<string, any> = {};
  const keyMap: Record<string, string> = {
    confirmedFacts: "confirmed_facts",
    factsLocked: "facts_locked",
    cvHtml: "cv_html",
    coverLetterHtml: "cover_letter_html",
    learningPlan: "learning_plan",
    cvVersions: "cv_versions",
    clVersions: "cl_versions",
    userId: "user_id",
    applicationId: "application_id",
  };

  for (const [k, v] of Object.entries(patch)) {
    dbPatch[keyMap[k] || k] = v;
  }

  const { error } = await supabase
    .from(TABLES.applications)
    .update(dbPatch)
    .eq("id", appId);

  if (error) throw error;
}

export async function deleteApplication(appId: string): Promise<void> {
  const { error } = await supabase
    .from(TABLES.applications)
    .delete()
    .eq("id", appId);

  if (error) throw error;
}

/* ================================================================== */
/*  MODULE STATUS                                                       */
/* ================================================================== */

export async function setModuleStatus(
  appId: string,
  moduleKey: ModuleKey,
  status: ModuleStatusState,
  errorMsg?: string
): Promise<void> {
  // First get current modules
  const { data, error: fetchErr } = await supabase
    .from(TABLES.applications)
    .select("modules")
    .eq("id", appId)
    .maybeSingle();

  if (fetchErr) throw fetchErr;

  const modules = data?.modules ?? { ...DEFAULT_MODULES };
  modules[moduleKey] = {
    state: status,
    ...(errorMsg ? { error: errorMsg } : {}),
    updatedAt: Date.now(),
  };

  const { error } = await supabase
    .from(TABLES.applications)
    .update({ modules })
    .eq("id", appId);

  if (error) throw error;
}

/* ================================================================== */
/*  GENERATION PIPELINE                                                 */
/* ================================================================== */

export async function generateApplicationModules(
  appId: string,
  userId: string,
  confirmedFacts: ConfirmedFacts,
  modules: ModuleKey[] = ["benchmark", "gaps", "learningPlan", "cv", "coverLetter", "scorecard"]
): Promise<void> {
  const jdText = confirmedFacts.jdText ?? "";
  const resumeText = confirmedFacts.resume?.text ?? "";
  const jobTitle = confirmedFacts.jobTitle ?? "";
  const company = confirmedFacts.company;
  const keywords = extractKeywords(jdText);

  for (const mod of modules) {
    try {
      await setModuleStatus(appId, mod, "generating");

      switch (mod) {
        case "benchmark": {
          const benchmark = buildBenchmark(jobTitle, company, keywords);
          await patchApplication(appId, {
            benchmark,
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
        case "gaps": {
          const gapResult = buildGaps(confirmedFacts, keywords);
          await patchApplication(appId, {
            gaps: {
              missingKeywords: gapResult.missingKeywords,
              strengths: gapResult.strengths,
              recommendations: gapResult.recommendations,
              gaps: gapResult.missingKeywords.map((kw) => ({
                dimension: "skills",
                gap: `Missing: ${kw}`,
                severity: "medium" as const,
                suggestion: `Add evidence of ${kw} experience`,
              })),
              summary: gapResult.summary,
            },
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
        case "learningPlan": {
          const gapData = buildGaps(confirmedFacts, keywords);
          const plan = buildLearningPlan(gapData.missingKeywords);
          await patchApplication(appId, {
            learningPlan: plan,
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
        case "cv": {
          const cvHtml = seedCvHtml(confirmedFacts, jobTitle, company, keywords, resumeText);
          await patchApplication(appId, {
            cvHtml,
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
        case "coverLetter": {
          const clHtml = seedCoverLetterHtml(confirmedFacts, jobTitle, company, keywords);
          await patchApplication(appId, {
            coverLetterHtml: clHtml,
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
        case "scorecard": {
          const matchScore = computeMatchScore(confirmedFacts, keywords);
          const gapResult = buildGaps(confirmedFacts, keywords);
          const atsScore = Math.min(100, matchScore + 10);
          const scanScore = Math.min(100, matchScore + 5);
          const topFix = deriveTopFix(gapResult.missingKeywords, computeJDQuality(jdText));
          const scorecard = buildScorecard({
            match: matchScore,
            ats: atsScore,
            scan: scanScore,
            evidence: 0,
            topFix,
          });
          await patchApplication(appId, {
            scorecard,
            scores: {
              match: matchScore,
              atsReadiness: atsScore,
              recruiterScan: scanScore,
              evidenceStrength: 0,
              topFix,
              benchmark: matchScore,
              gaps: Math.max(0, 100 - gapResult.missingKeywords.length * 10),
              cv: matchScore,
              coverLetter: matchScore,
              overall: matchScore,
            },
            modules: await getModules(appId, mod, "ready"),
          });
          break;
        }
      }
    } catch (err: any) {
      await setModuleStatus(appId, mod, "error", err.message);
    }
  }
}

async function getModules(
  appId: string,
  justFinished: ModuleKey,
  newStatus: ModuleStatusState
): Promise<Record<ModuleKey, ModuleStatus>> {
  const { data } = await supabase
    .from(TABLES.applications)
    .select("modules")
    .eq("id", appId)
    .maybeSingle();

  const modules = data?.modules ?? { ...DEFAULT_MODULES };
  modules[justFinished] = { state: newStatus, updatedAt: Date.now() };
  return modules;
}

/* ================================================================== */
/*  MODULE RE-GENERATION                                                */
/* ================================================================== */

export async function regenerateModule(
  appIdOrOpts: string | { userId: string; appId: string; module: ModuleKey; evidenceCount?: number },
  moduleKey?: ModuleKey
): Promise<void> {
  let resolvedAppId: string;
  let resolvedKey: ModuleKey;

  if (typeof appIdOrOpts === "object") {
    resolvedAppId = appIdOrOpts.appId;
    resolvedKey = appIdOrOpts.module;
  } else {
    resolvedAppId = appIdOrOpts;
    resolvedKey = moduleKey!;
  }

  const app = await getApplication(resolvedAppId);
  if (!app?.confirmedFacts) return;
  await generateApplicationModules(resolvedAppId, app.userId, app.confirmedFacts, [resolvedKey]);
}

/* ================================================================== */
/*  DOC VERSIONING                                                      */
/* ================================================================== */

export async function snapshotDocVersion(
  appId: string,
  docType: "cv" | "coverLetter",
  labelOrHtml?: string,
  label?: string
): Promise<void> {
  const versionId = uid("ver");
  const colKey = docType === "cv" ? "cv_versions" : "cl_versions";
  const htmlColKey = docType === "cv" ? "cv_html" : "cover_letter_html";

  // Get current app data for versions and html
  const { data } = await supabase
    .from(TABLES.applications)
    .select(`${colKey}, ${htmlColKey}`)
    .eq("id", appId)
    .maybeSingle() as { data: any };

  // If 4 args: (appId, docType, html, label) — explicit html
  // If 3 args: (appId, docType, label) — html from DB
  let html: string;
  let resolvedLabel: string | undefined;
  if (label !== undefined) {
    // 4-arg form
    html = labelOrHtml || "";
    resolvedLabel = label;
  } else {
    // 3-arg form — labelOrHtml is the label, html comes from DB
    html = data?.[htmlColKey] ?? "";
    resolvedLabel = labelOrHtml;
  }

  const versions: DocVersion[] = data?.[colKey] ?? [];
  versions.unshift({
    id: versionId,
    html,
    label: resolvedLabel,
    createdAt: Date.now(),
  });

  // Keep max 20 versions
  const trimmed = versions.slice(0, 20);

  await supabase
    .from(TABLES.applications)
    .update({ [colKey]: trimmed })
    .eq("id", appId);
}

export async function restoreDocVersion(
  appId: string,
  docType: "cv" | "coverLetter",
  versionId: string
): Promise<void> {
  const colKey = docType === "cv" ? "cv_versions" : "cl_versions";
  const htmlKey = docType === "cv" ? "cv_html" : "cover_letter_html";

  const { data } = await supabase
    .from(TABLES.applications)
    .select(colKey)
    .eq("id", appId)
    .maybeSingle() as { data: any };

  const versions: DocVersion[] = data?.[colKey] ?? [];
  const version = versions.find((v) => v.id === versionId);
  if (!version) return;

  await supabase
    .from(TABLES.applications)
    .update({ [htmlKey]: version.html })
    .eq("id", appId);
}

/* ================================================================== */
/*  EVIDENCE CRUD                                                       */
/* ================================================================== */

export async function createEvidence(
  userId: string,
  evidence: Omit<EvidenceDoc, "id" | "createdAt" | "updatedAt">
): Promise<string> {
  const row = {
    user_id: userId,
    application_id: evidence.applicationId ?? null,
    kind: evidence.kind ?? "link",
    type: evidence.type,
    title: evidence.title,
    description: evidence.description ?? null,
    url: evidence.url ?? null,
    storage_url: evidence.storageUrl ?? null,
    file_url: evidence.fileUrl ?? null,
    file_name: evidence.fileName ?? null,
    skills: evidence.skills ?? [],
    tools: evidence.tools ?? [],
    tags: evidence.tags ?? [],
  };

  const { data, error } = await supabase.from(TABLES.evidence).insert(row).select("id").single();
  if (error) throw error;
  return data.id;
}

export async function deleteEvidence(evidenceId: string): Promise<void> {
  const { error } = await supabase
    .from(TABLES.evidence)
    .delete()
    .eq("id", evidenceId);

  if (error) throw error;
}

/* ================================================================== */
/*  TASK CRUD                                                           */
/* ================================================================== */

export async function upsertTask(task: Partial<TaskDoc> & { id: string; userId: string }): Promise<void> {
  const row: Record<string, any> = {
    id: task.id,
    user_id: task.userId,
  };
  if (task.applicationId !== undefined) row.application_id = task.applicationId;
  if (task.source !== undefined) row.source = task.source;
  if (task.title !== undefined) row.title = task.title;
  if (task.description !== undefined) row.description = task.description;
  if (task.status !== undefined) row.status = task.status;
  if (task.priority !== undefined) row.priority = task.priority;

  const { error } = await supabase
    .from(TABLES.tasks)
    .upsert(row, { onConflict: "id" });

  if (error) throw error;
}

export async function setTaskStatus(
  _userIdOrTaskId: string,
  taskIdOrStatus: string,
  maybeStatus?: TaskDoc["status"]
): Promise<void> {
  // Support both (taskId, status) and (userId, taskId, status) call patterns
  const taskId = maybeStatus !== undefined ? taskIdOrStatus : _userIdOrTaskId;
  const status = (maybeStatus !== undefined ? maybeStatus : taskIdOrStatus) as TaskDoc["status"];

  const { error } = await supabase
    .from(TABLES.tasks)
    .update({ status })
    .eq("id", taskId);

  if (error) throw error;
}

/* ================================================================== */
/*  EVENT TRACKING                                                      */
/* ================================================================== */

export async function trackEvent(
  userId: string,
  eventOrObj: string | { name: string; appId?: string; properties?: Record<string, any> },
  applicationId?: string,
  payload?: Record<string, any>
): Promise<void> {
  let event: string;
  let appId: string | null = applicationId ?? null;
  let eventPayload: Record<string, any> | null = payload ?? null;

  if (typeof eventOrObj === "object") {
    event = eventOrObj.name;
    appId = eventOrObj.appId ?? null;
    eventPayload = eventOrObj.properties ?? null;
  } else {
    event = eventOrObj;
  }

  const { error } = await supabase.from(TABLES.events).insert({
    user_id: userId,
    application_id: appId,
    event,
    payload: eventPayload,
  });

  if (error) {
    console.error("trackEvent failed:", error);
  }
}

/* ================================================================== */
/*  FILE UPLOAD — Supabase Storage                                      */
/* ================================================================== */

export async function uploadFile(
  bucket: string,
  path: string,
  file: File
): Promise<string> {
  const { error } = await supabase.storage.from(bucket).upload(path, file, {
    upsert: true,
    contentType: file.type,
  });
  if (error) throw error;

  const { data } = supabase.storage.from(bucket).getPublicUrl(path);
  return data.publicUrl;
}

export async function uploadResume(
  userId: string,
  file: File
): Promise<string> {
  const ext = file.name.split(".").pop() ?? "pdf";
  const path = `${userId}/${uid("resume")}.${ext}`;
  return uploadFile("resumes", path, file);
}

export async function uploadEvidenceFile(
  userId: string,
  file: File
): Promise<string> {
  const ext = file.name.split(".").pop() ?? "pdf";
  const path = `${userId}/${uid("file")}.${ext}`;
  return uploadFile("evidence", path, file);
}

/* ================================================================== */
/*  JD QUALITY ANALYSIS                                                 */
/* ================================================================== */

export function computeJDQuality(
  jdText: string
): JDQuality & { issues: string[]; suggestions: string[] } {
  const text = (jdText || "").trim();
  const issues: string[] = [];
  const suggestions: string[] = [];
  let score = 100;

  // Length check
  if (text.length < 100) {
    score -= 30;
    issues.push("Very short JD — less than 100 characters");
    suggestions.push("Add more detail about the role, requirements, and responsibilities");
  } else if (text.length < 300) {
    score -= 15;
    issues.push("Short JD — could benefit from more detail");
    suggestions.push("Expand the responsibilities and requirements sections");
  }

  // Section checks
  const lower = text.toLowerCase();

  if (!/responsibilit|duties|what you.?ll do|role overview/i.test(text)) {
    score -= 15;
    issues.push("Missing responsibilities section");
    suggestions.push("Add a responsibilities or duties section");
  }

  if (!/requirement|qualif|what we.?re looking|must have|experience/i.test(text)) {
    score -= 15;
    issues.push("Missing requirements section");
    suggestions.push("Add a requirements or qualifications section");
  }

  // Bullet points
  const bullets = (text.match(/[-•*]\s|^\d+\./gm) || []).length;
  if (bullets < 3) {
    score -= 10;
    issues.push("Few or no bullet points found");
    suggestions.push("Use bullet points to list responsibilities and requirements");
  }

  // Tech keywords
  const techTerms = extractKeywords(text);
  if (techTerms.length < 3) {
    score -= 10;
    issues.push("Few technical terms detected");
    suggestions.push("Include specific technologies, tools, and skills");
  }

  score = Math.max(0, Math.min(100, score));

  return {
    score,
    flags: issues,
    summary:
      score >= 80
        ? "Strong JD with good detail"
        : score >= 50
        ? "Moderate JD — consider adding more detail"
        : "Weak JD — significantly expand requirements and responsibilities",
    issues,
    suggestions,
  };
}

/* ================================================================== */
/*  KEYWORD EXTRACTION                                                  */
/* ================================================================== */

const STOPWORDS = new Set([
  "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
  "have", "has", "had", "do", "does", "did", "will", "would", "shall",
  "should", "may", "might", "must", "can", "could", "am", "in", "on",
  "at", "to", "for", "of", "with", "by", "from", "as", "into", "through",
  "during", "before", "after", "above", "below", "between", "under",
  "again", "further", "then", "once", "here", "there", "when", "where",
  "why", "how", "all", "each", "every", "both", "few", "more", "most",
  "other", "some", "such", "no", "not", "only", "own", "same", "so",
  "than", "too", "very", "just", "because", "but", "and", "or", "if",
  "while", "about", "against", "over", "this", "that", "these", "those",
  "it", "its", "we", "our", "you", "your", "they", "them", "their",
  "he", "she", "his", "her", "what", "which", "who", "whom",
  "work", "team", "role", "experience", "skills", "ability", "using",
  "working", "including", "strong", "knowledge", "understanding", "years",
]);

const KNOWN_SKILLS = new Set([
  "javascript", "typescript", "python", "java", "go", "rust", "ruby", "php",
  "swift", "kotlin", "scala", "elixir", "clojure", "haskell",
  "react", "angular", "vue", "svelte", "next", "nuxt", "remix",
  "node", "nodejs", "express", "fastapi", "django", "flask", "rails", "spring",
  "sql", "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
  "firebase", "supabase", "dynamodb", "cassandra",
  "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
  "git", "github", "gitlab", "bitbucket", "jenkins", "ci", "cd",
  "graphql", "rest", "grpc", "websocket", "microservices",
  "tailwind", "css", "sass", "html",
  "jest", "vitest", "playwright", "cypress", "selenium",
  "figma", "sketch", "design", "ux", "ui",
  "agile", "scrum", "kanban", "jira",
  "machine", "learning", "ai", "ml", "nlp", "pytorch", "tensorflow",
  "linux", "unix", "bash", "shell",
]);

const SKILL_ALIASES: Record<string, string> = {
  nodejs: "node", nextjs: "next", nuxtjs: "nuxt", vuejs: "vue",
  reactjs: "react", angularjs: "angular", expressjs: "express",
  postgresql: "postgres",
};

export function extractKeywords(text: string, max = 30): string[] {
  if (!text) return [];

  const words = text
    .toLowerCase()
    .replace(/[^a-z0-9\s+#.]/g, " ")
    .split(/\s+/)
    .map((w) => w.replace(/^\.+|\.+$/g, ""))
    .filter(Boolean);

  const seen = new Set<string>();
  const result: string[] = [];

  for (const word of words) {
    let clean = word.replace(/[.+#]/g, "").toLowerCase();
    if (clean.length < 2) continue;
    if (STOPWORDS.has(clean)) continue;

    // Normalize aliases (nodejs → node, etc.)
    clean = SKILL_ALIASES[clean] ?? clean;
    if (seen.has(clean)) continue;

    // Prefer known skills
    if (KNOWN_SKILLS.has(clean)) {
      seen.add(clean);
      result.push(clean);
    }
  }

  // Also add any significant non-stopword terms if we didn't hit many skills
  if (result.length < 5) {
    for (const word of words) {
      let clean = word.replace(/[.+#]/g, "").toLowerCase();
      clean = SKILL_ALIASES[clean] ?? clean;
      if (clean.length < 3) continue;
      if (STOPWORDS.has(clean)) continue;
      if (seen.has(clean)) continue;
      seen.add(clean);
      result.push(clean);
      if (result.length >= max) break;
    }
  }

  return result.slice(0, max);
}

/* ================================================================== */
/*  MATCH / COVERAGE SCORES                                             */
/* ================================================================== */

export function computeMatchScore(
  facts: ConfirmedFacts | null,
  keywords: string[]
): number {
  if (!facts || keywords.length === 0) return 0;

  const resumeWords = new Set(
    [
      ...(facts.resume?.text ?? "").toLowerCase().split(/\s+/),
      ...(facts.jdText ?? "").toLowerCase().split(/\s+/),
    ].map((w) => w.replace(/[^a-z0-9]/g, ""))
  );

  let matched = 0;
  for (const kw of keywords) {
    if (resumeWords.has(kw.toLowerCase())) matched++;
  }

  return Math.round((matched / keywords.length) * 100);
}

export function computeDocCoverageScore(
  html: string,
  keywords: string[]
): number {
  if (!html || keywords.length === 0) return 0;

  const text = (html || "")
    .replace(/<[^>]*>/g, " ")
    .toLowerCase();

  let matched = 0;
  for (const kw of keywords) {
    if (text.includes(kw.toLowerCase())) matched++;
  }

  return Math.round((matched / keywords.length) * 100);
}

/* ================================================================== */
/*  TOP FIX                                                             */
/* ================================================================== */

export function deriveTopFix(
  missingKeywords: string[],
  jdQuality: { score: number; issues: string[]; suggestions: string[] }
): string {
  if (missingKeywords.length > 0) {
    return `Add proof for "${missingKeywords[0]}" — include a concrete project or measurable result.`;
  }
  if (jdQuality.score < 60) {
    return "Strengthen the JD — add responsibilities, requirements, and technical keywords.";
  }
  return "Tighten your summary — lead with the strongest proof point for this role.";
}

/* ================================================================== */
/*  MODULE BUILDERS                                                     */
/* ================================================================== */

export function buildBenchmark(
  jobTitle: string,
  company: string | undefined,
  keywords: string[]
): {
  summary: string;
  keywords: string[];
  rubric: string[];
  createdAt: number;
} {
  const companyStr = company ? ` at ${company}` : "";
  return {
    summary: `Benchmark for ${jobTitle}${companyStr} — ${keywords.length} key dimensions identified.`,
    keywords,
    rubric: keywords.slice(0, 6).map((kw) =>
      `${kw.charAt(0).toUpperCase() + kw.slice(1)} — proficiency, production application & leadership`
    ),
    createdAt: Date.now(),
  };
}

export function buildGaps(
  facts: ConfirmedFacts | null,
  keywords: string[]
): {
  missingKeywords: string[];
  strengths: string[];
  summary: string;
  recommendations: string[];
} {
  const resumeText = (facts?.resume?.text ?? "").toLowerCase();
  const skills = (facts as any)?.skills ?? [];
  const skillsLower = skills.map((s: string) => s.toLowerCase());

  const missingKeywords: string[] = [];
  const strengths: string[] = [];

  for (const kw of keywords) {
    const kwLower = kw.toLowerCase();
    if (resumeText.includes(kwLower) || skillsLower.includes(kwLower)) {
      // It's a strength — use original case from skills if available
      const original = skills.find((s: string) => s.toLowerCase() === kwLower);
      strengths.push(original || kw);
    } else {
      missingKeywords.push(kw);
    }
  }

  // If no facts at all, everything is missing
  if (!facts) {
    return {
      missingKeywords: [...keywords],
      strengths: [],
      summary: "No resume data available — upload a resume to identify gaps.",
      recommendations: keywords.map((kw) => `Develop evidence for ${kw}`),
    };
  }

  return {
    missingKeywords,
    strengths,
    summary:
      missingKeywords.length === 0
        ? "Great coverage — all key skills matched!"
        : `${missingKeywords.length} gap${missingKeywords.length > 1 ? "s" : ""} identified: ${missingKeywords.join(", ")}`,
    recommendations: missingKeywords.map(
      (kw) => `Build proof for ${kw}: add a project, cert, or measurable achievement.`
    ),
  };
}

export function buildLearningPlan(missingKeywords: string[]): {
  focus: string[];
  plan: { week: number; theme: string; outcomes: string[]; tasks: string[]; goals: string[] }[];
  resources: { skill: string; title: string; provider: string; timebox: string; url?: string }[];
} {
  return {
    focus: [...missingKeywords],
    plan: [1, 2, 3, 4].map((week) => {
      const skill = missingKeywords[(week - 1) % missingKeywords.length] ?? "core skills";
      return {
        week,
        theme: missingKeywords.length > 0 ? `${skill} Sprint` : `Week ${week}: Strengthen foundations`,
        outcomes:
          missingKeywords.length > 0
            ? [`Demonstrate ${skill} proficiency through a mini-project or proof artifact`]
            : [`Reinforce existing strengths and explore adjacent areas`],
        tasks:
          missingKeywords.length > 0
            ? [
                `Deep-dive into ${skill}`,
                `Complete a hands-on exercise for ${skill}`,
                `Document evidence of ${skill} competency`,
              ]
            : [`Review and polish existing skill evidence`, `Explore adjacent skill areas`],
        goals:
          missingKeywords.length > 0
            ? [`Week ${week}: Deep-dive into ${skill}`]
            : [`Week ${week}: Reinforce existing strengths and explore adjacent areas`],
      };
    }),
    resources: missingKeywords.map((skill) => ({
      skill,
      title: `${skill.charAt(0).toUpperCase() + skill.slice(1)} — Recommended Learning`,
      provider: "Self-paced",
      timebox: "1–2 hours",
      url: `https://www.google.com/search?q=${encodeURIComponent(skill + " tutorial")}`,
    })),
  };
}

export function buildScorecard(input: {
  match: number;
  ats: number;
  scan: number;
  evidence: number;
  topFix: string;
}): Scorecard & {
  match: number;
  atsReadiness: number;
  recruiterScan: number;
  evidenceStrength: number;
  topFix: string;
  updatedAt: number;
} {
  const clamp = (v: number) => Math.max(0, Math.min(100, v));
  const match = clamp(input.match);
  const ats = clamp(input.ats);
  const scan = clamp(input.scan);
  const ev = clamp(input.evidence);

  return {
    overall: Math.round((match + ats + scan + ev) / 4),
    dimensions: [
      { name: "Match", score: match, feedback: `${match}% keyword match` },
      { name: "ATS Readiness", score: ats, feedback: `${ats}% ATS-friendly` },
      { name: "Recruiter Scan", score: scan, feedback: `${scan}% scannable` },
      { name: "Evidence Strength", score: ev, feedback: `${ev}% backed by proof` },
    ],
    match,
    atsReadiness: ats,
    recruiterScan: scan,
    evidenceStrength: ev,
    topFix: input.topFix,
    updatedAt: Date.now(),
  };
}

/* ================================================================== */
/*  COACH ACTIONS                                                       */
/* ================================================================== */

export function buildCoachActions(ctx: {
  missingKeywords: string[];
  factsLocked: boolean;
  evidenceCount: number;
}): { kind: "fix" | "write" | "collect" | "review"; title: string; why: string; cta: string }[] {
  if (!ctx.factsLocked) {
    return [
      {
        kind: "review",
        title: "Lock your confirmed facts",
        why: "Review and confirm your JD + resume data before generating modules.",
        cta: "Review facts",
      },
    ];
  }

  if (ctx.evidenceCount === 0) {
    return [
      {
        kind: "collect",
        title: "Collect evidence",
        why: "Upload certificates, project links, or other proof to strengthen your application.",
        cta: "Open vault",
      },
    ];
  }

  if (ctx.missingKeywords.length > 0) {
    return [
      {
        kind: "fix",
        title: `Add proof for ${ctx.missingKeywords[0]}`,
        why: `You're missing evidence for ${ctx.missingKeywords[0]}. Add a project or cert.`,
        cta: "Fix in CV",
      },
    ];
  }

  return [
    {
      kind: "write",
      title: "Take a snapshot",
      why: "All modules look good. Snapshot your CV and cover letter versions.",
      cta: "Open versions",
    },
  ];
}

/* ================================================================== */
/*  DOCUMENT SEED GENERATORS                                            */
/* ================================================================== */

export function seedCvHtml(
  facts: ConfirmedFacts | null,
  jobTitle: string,
  company: string | undefined,
  keywords: string[],
  baseResume?: string
): string {
  const name = (facts as any)?.fullName ?? "Your Name";
  const headline = (facts as any)?.headline ?? jobTitle;
  const companyStr = company ? ` — ${company}` : "";

  let html = `<h1>${name}</h1>`;
  html += `<h2>${headline}${companyStr}</h2>`;
  html += `<hr/>`;

  if (keywords.length > 0) {
    html += `<h3>Role Keywords</h3>`;
    html += `<p>${keywords.join(", ")}</p>`;
  }

  html += `<h3>Proof Hooks</h3>`;
  html += `<ul>`;
  for (const kw of keywords.slice(0, 5)) {
    html += `<li>[${kw}] — Add a concrete achievement here</li>`;
  }
  html += `</ul>`;

  if (baseResume) {
    html += `<h3>Base Resume</h3>`;
    html += baseResume;
  }

  return html;
}

export function seedCoverLetterHtml(
  facts: ConfirmedFacts | null,
  jobTitle: string,
  company: string | undefined,
  keywords: string[]
): string {
  const name = (facts as any)?.fullName ?? "Your Name";
  const companyStr = company ?? "the company";

  let html = `<h2>Cover Letter</h2>`;
  html += `<p>Dear Hiring Manager at ${companyStr},</p>`;
  html += `<p>I am writing to express my interest in the ${jobTitle} position. `;
  html += `With my background in ${keywords.slice(0, 3).join(", ")}, `;
  html += `I am confident in my ability to contribute to your team.</p>`;
  html += `<p>[Add specific achievements and proof points here]</p>`;
  html += `<p>Sincerely,<br/>${name}</p>`;

  return html;
}

/* ================================================================== */
/*  EMPTY DOC MODULE HELPER                                             */
/* ================================================================== */

export function emptyDocModule(seedHtml = ""): {
  contentHtml: string;
  versions: DocVersion[];
  updatedAt: number;
} {
  return {
    contentHtml: seedHtml,
    versions: [],
    updatedAt: Date.now(),
  };
}
