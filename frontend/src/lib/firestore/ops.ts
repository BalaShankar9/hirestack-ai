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
  GenerationJobDoc,
  GenerationJobEventDoc,
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
  personalStatement: { state: "idle" },
  portfolio: { state: "idle" },
  scorecard: { state: "idle" },
};

export function mapApplicationRow(row: any): ApplicationDoc {
  // Coerce scores.topFix to a string if it's an object (defensive against bad JSONB)
  let scores = row.scores ?? undefined;
  if (scores && typeof scores.topFix !== "undefined" && typeof scores.topFix !== "string") {
    const tf = scores.topFix;
    scores = {
      ...scores,
      topFix: String(tf?.dimension ?? tf?.title ?? tf?.message ?? JSON.stringify(tf)),
    };
  }

  return {
    id: row.id,
    userId: row.user_id,
    title: row.title ?? "",
    status: row.status ?? "draft",
    createdAt: ts(row.created_at),
    updatedAt: ts(row.updated_at),
    confirmedFacts: row.confirmed_facts ?? undefined,
    factsLocked: row.facts_locked ?? false,
    modules: { ...DEFAULT_MODULES, ...(row.modules ?? {}) },
    benchmark: row.benchmark ?? undefined,
    gaps: row.gaps ?? undefined,
    learningPlan: row.learning_plan ?? undefined,
    cvHtml: row.cv_html ?? undefined,
    coverLetterHtml: row.cover_letter_html ?? undefined,
    personalStatementHtml: row.personal_statement_html ?? undefined,
    portfolioHtml: row.portfolio_html ?? undefined,
    scorecard: row.scorecard ?? undefined,
    validation: row.validation ?? undefined,
    scores,
    cvVersions: Array.isArray(row.cv_versions) ? row.cv_versions : [],
    clVersions: Array.isArray(row.cl_versions) ? row.cl_versions : [],
    psVersions: Array.isArray(row.ps_versions) ? row.ps_versions : [],
    portfolioVersions: Array.isArray(row.portfolio_versions) ? row.portfolio_versions : [],
    discoveredDocuments: row.discovered_documents ?? undefined,
    generatedDocuments: row.generated_documents ?? undefined,
    benchmarkDocuments: row.benchmark_documents ?? undefined,
    documentStrategy: row.document_strategy ?? undefined,
    companyIntel: row.company_intel ?? undefined,
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
    skills: Array.isArray(row.skills) ? row.skills : [],
    tools: Array.isArray(row.tools) ? row.tools : [],
    tags: Array.isArray(row.tags) ? row.tags : [],
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
    detail: row.detail ?? undefined,
    why: row.why ?? undefined,
    status: row.status ?? "todo",
    priority: row.priority ?? "medium",
    dueDate: row.due_date ? ts(row.due_date) : undefined,
    createdAt: ts(row.created_at),
    updatedAt: ts(row.updated_at),
  };
}

export function mapGenerationJobRow(row: any): GenerationJobDoc {
  return {
    id: row.id,
    userId: row.user_id,
    applicationId: row.application_id,
    requestedModules: Array.isArray(row.requested_modules) ? row.requested_modules : [],
    status: row.status ?? "queued",
    progress: typeof row.progress === "number" ? row.progress : 0,
    phase: row.phase ?? undefined,
    message: row.message ?? undefined,
    cancelRequested: row.cancel_requested ?? false,
    currentAgent: row.current_agent ?? undefined,
    completedSteps: typeof row.completed_steps === "number" ? row.completed_steps : 0,
    totalSteps: typeof row.total_steps === "number" ? row.total_steps : 0,
    activeSourcesCount: typeof row.active_sources_count === "number" ? row.active_sources_count : 0,
    result: row.result ?? undefined,
    errorMessage: row.error_message ?? undefined,
    createdAt: ts(row.created_at),
    startedAt: row.started_at ? ts(row.started_at) : undefined,
    finishedAt: row.finished_at ? ts(row.finished_at) : undefined,
    updatedAt: ts(row.updated_at),
  };
}

export function mapGenerationJobEventRow(row: any): GenerationJobEventDoc {
  return {
    id: String(row.id),
    jobId: row.job_id,
    userId: row.user_id,
    applicationId: row.application_id,
    sequenceNo: typeof row.sequence_no === "number" ? row.sequence_no : 0,
    eventName: row.event_name ?? "progress",
    agentName: row.agent_name ?? undefined,
    stage: row.stage ?? undefined,
    status: row.status ?? undefined,
    message: row.message ?? "",
    source: row.source ?? undefined,
    url: row.url ?? undefined,
    latencyMs: typeof row.latency_ms === "number" ? row.latency_ms : undefined,
    payload: row.payload ?? undefined,
    createdAt: ts(row.created_at),
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
    personalStatementHtml: "personal_statement_html",
    portfolioHtml: "portfolio_html",
    learningPlan: "learning_plan",
    cvVersions: "cv_versions",
    clVersions: "cl_versions",
    psVersions: "ps_versions",
    portfolioVersions: "portfolio_versions",
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
/*  GENERATION PIPELINE — AI-powered via backend                       */
/* ================================================================== */

// Prefer IPv4 loopback to avoid environments where `localhost` resolves to IPv6 (::1)
// while the backend is bound to 127.0.0.1.
const AI_API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/** Progress event emitted by the SSE streaming pipeline */
export interface PipelineProgress {
  phase: string;
  step: number;
  totalSteps: number;
  progress: number;
  message: string;
}

export interface PipelineAgentEvent {
  pipeline_name: string;
  stage: string;
  status: string;
  latency_ms: number;
  message: string;
  timestamp?: string;
}

export interface PipelineDetailEvent {
  agent: string;
  message: string;
  status: string;
  source?: string;
  url?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
}

export async function cancelGenerationJob(jobId: string): Promise<void> {
  // getUser() triggers a token refresh if the session is stale
  await supabase.auth.getUser();
  const { data: sessionData } = await supabase.auth.getSession();
  const accessToken = sessionData.session?.access_token ?? null;
  if (!accessToken) throw new Error("Authentication required");

  const response = await fetch(`${AI_API_URL}/api/generate/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    const errBody = await response.text().catch(() => "");
    throw new Error(errBody || `Failed to cancel generation job (${response.status})`);
  }
}

function uuidv4(): string {
  const c: any = typeof globalThis !== "undefined" ? (globalThis as any).crypto : undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();

  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function syncAutoTasks(
  appId: string,
  userId: string,
  gaps: any | undefined,
  learningPlan: any | undefined
): Promise<void> {
  const sources = ["gaps", "learningPlan"] as const;

  const { data: existingRows, error: existingErr } = await supabase
    .from(TABLES.tasks)
    .select("id, source, title, status")
    .eq("user_id", userId)
    .eq("application_id", appId)
    .in("source", sources as unknown as string[]);

  if (existingErr) throw existingErr;

  const existingByKey = new Map<string, { id: string; status: TaskDoc["status"] }>();
  for (const row of existingRows ?? []) {
    const key = `${row.source}:${row.title}`;
    existingByKey.set(key, { id: row.id, status: row.status ?? "todo" });
  }

  const candidates: Array<Omit<TaskDoc, "createdAt" | "updatedAt">> = [];

  const missingKeywords: string[] = Array.isArray(gaps?.missingKeywords)
    ? (gaps.missingKeywords as any[]).filter((k) => typeof k === "string")
    : [];
  const topMissing = missingKeywords.slice(0, 8);
  for (let idx = 0; idx < topMissing.length; idx++) {
    const kw = topMissing[idx]?.trim?.() ?? String(topMissing[idx] ?? "").trim();
    if (!kw) continue;
    candidates.push({
      id: "",
      userId,
      applicationId: appId,
      appId,
      source: "gaps",
      title: `Add proof for ${kw}`,
      description: `Create one concrete artifact (project, certification, or link) that demonstrates ${kw}, then attach it in Evidence.`,
      detail: `Missing keyword: ${kw}`,
      why: `This keyword appears in the JD signal. Proof-backed keywords improve match and credibility.`,
      status: "todo",
      priority: idx < 3 ? "high" : "medium",
    });
  }

  const planWeeks: any[] = Array.isArray(learningPlan?.plan) ? learningPlan.plan : [];
  for (const week of planWeeks.slice(0, 3)) {
    const weekNum = typeof week?.week === "number" ? week.week : undefined;
    const theme = typeof week?.theme === "string" ? week.theme : "Learning sprint";
    const tasks: string[] = Array.isArray(week?.tasks)
      ? (week.tasks as any[]).filter((t) => typeof t === "string")
      : [];
    for (const task of tasks.slice(0, 2)) {
      const text = task.trim();
      if (!text) continue;
      const titleCore = text.length > 80 ? `${text.slice(0, 77)}…` : text;
      candidates.push({
        id: "",
        userId,
        applicationId: appId,
        appId,
        source: "learningPlan",
        title: weekNum ? `Week ${weekNum}: ${titleCore}` : titleCore,
        description: text,
        detail: theme,
        why: "Each learning sprint should produce a proof artifact you can attach to your application.",
        status: "todo",
        priority: "medium",
      });
    }
  }

  const seen = new Set<string>();
  for (const candidate of candidates) {
    const key = `${candidate.source}:${candidate.title}`;
    if (seen.has(key)) continue;
    seen.add(key);

    const existing = existingByKey.get(key);
    if (existing) {
      // Preserve completion state; refresh metadata for open tasks.
      if (existing.status === "done" || existing.status === "skipped") continue;
      await upsertTask({
        ...candidate,
        id: existing.id,
        userId,
        status: existing.status,
      });
      continue;
    }

    await upsertTask({
      ...candidate,
      id: uuidv4(),
      userId,
    });
  }
}

export async function generateApplicationModules(
  appId: string,
  userId: string,
  confirmedFacts: ConfirmedFacts,
  modules: ModuleKey[] = ["benchmark", "gaps", "learningPlan", "cv", "coverLetter", "personalStatement", "portfolio", "scorecard"],
  onProgress?: (p: PipelineProgress) => void,
  opts?: {
    signal?: AbortSignal;
    onAgentEvent?: (event: PipelineAgentEvent) => void;
    onDetailEvent?: (event: PipelineDetailEvent) => void;
    onJobCreated?: (jobId: string) => void;
  },
): Promise<void> {
  const jdText = confirmedFacts.jdText ?? "";
  const resumeText = confirmedFacts.resume?.text ?? "";
  const jobTitle = confirmedFacts.jobTitle ?? "";
  const company = confirmedFacts.company;

  // Set modules to "generating" (single DB update; preserves other module states)
  let moduleStates: Record<ModuleKey, ModuleStatus> = { ...DEFAULT_MODULES } as any;
  const { data: modRow } = await supabase
    .from(TABLES.applications)
    .select("modules")
    .eq("id", appId)
    .maybeSingle();

  moduleStates = (modRow?.modules ?? moduleStates) as any;
  const generatingAt = Date.now();
  for (const mod of modules) {
    moduleStates[mod] = { state: "generating", updatedAt: generatingAt };
  }

  await supabase
    .from(TABLES.applications)
    .update({ modules: moduleStates })
    .eq("id", appId);

  const MAX_RETRIES = 3;
  let lastError: Error | null = null;
  let cancelledByUserViaJob = false;
  let persistedJobId: string | null = null;
  let serverOwnsPersistence = false;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    let abortedBy: "user" | "hard_timeout" | "inactivity" | null = null;
    let jobId: string | null = persistedJobId;
    let usedJobApi = false;
    try {
      const controller = new AbortController();
      // Hard timeout: allow long generations (local LLMs can take 10+ minutes).
      // Configurable via NEXT_PUBLIC_AI_HARD_TIMEOUT_MS.
      const hardTimeoutMsRaw = Number.parseInt(process.env.NEXT_PUBLIC_AI_HARD_TIMEOUT_MS ?? "", 10);
      const hardTimeoutMs = Number.isFinite(hardTimeoutMsRaw) && hardTimeoutMsRaw > 0 ? hardTimeoutMsRaw : 1_800_000;
      const hardTimeout = setTimeout(() => {
        abortedBy = abortedBy ?? "hard_timeout";
        controller.abort();
      }, hardTimeoutMs);

      console.log(`[HireStack] AI pipeline attempt ${attempt}/${MAX_RETRIES} (streaming)...`);

      // getUser() validates the token with Supabase and triggers a refresh if
      // the access token is expired — ensures we always send a fresh token.
      const { error: userErr } = await supabase.auth.getUser();
      if (userErr) throw new Error("Authentication required to generate documents");
      const { data: sessionData } = await supabase.auth.getSession();
      const accessToken = sessionData.session?.access_token ?? null;
      if (!accessToken) throw new Error("Authentication required to generate documents");

      // Prefer DB-backed generation jobs (resilient to refresh/disconnect).
      // Falls back to legacy /pipeline/stream if the endpoint isn't available.
      const cancelJobBestEffort = async () => {
        if (!jobId) return;
        try {
          await fetch(`${AI_API_URL}/api/generate/jobs/${jobId}/cancel`, {
            method: "POST",
            headers: { Authorization: `Bearer ${accessToken}` },
          });
        } catch {
          // ignore — cancellation is best-effort
        }
      };

      let response: Response | null = null;
      let useLegacyStream = false;

      try {
        if (jobId) {
          usedJobApi = true;
          response = await fetch(`${AI_API_URL}/api/generate/jobs/${jobId}/stream`, {
            method: "GET",
            headers: {
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
            signal: controller.signal,
          });
        } else {
          const jobResp = await fetch(`${AI_API_URL}/api/generate/jobs`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
            body: JSON.stringify({
              application_id: appId,
              requested_modules: modules,
            }),
            signal: controller.signal,
          });

          if (jobResp.ok) {
            const jobJson = await jobResp.json().catch(() => ({}));
            jobId = String(jobJson.job_id || jobJson.jobId || "");
            if (!jobId) throw new Error("Job API returned no job_id");
            persistedJobId = jobId;
            serverOwnsPersistence = true;
            usedJobApi = true;
            opts?.onJobCreated?.(jobId);

            response = await fetch(`${AI_API_URL}/api/generate/jobs/${jobId}/stream`, {
              method: "GET",
              headers: {
                ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
              },
              signal: controller.signal,
            });
          } else if (jobResp.status === 404 || jobResp.status === 503) {
            const errBody = await jobResp.text().catch(() => "");
            try {
              const parsed = JSON.parse(errBody);
              const detail = String(parsed?.detail ?? "");
              if (
                detail === "Not Found"
                || (jobResp.status === 503 && /schema not ready|database migrations/i.test(detail))
              ) {
                useLegacyStream = true;
              }
            } catch {
              if (jobResp.status === 503 && /schema not ready|database migrations/i.test(errBody)) {
                useLegacyStream = true;
              }
            }
            if (!useLegacyStream) {
              throw Object.assign(new Error(errBody || "Job creation failed"), {
                code: jobResp.status,
                nonRetryable: true,
              });
            }
            throw new Error("jobs-api-unavailable");
          } else {
            const errBody = await jobResp.text().catch(() => "");
            let userMessage: string;
            try {
              const parsed = JSON.parse(errBody);
              userMessage = parsed.detail ?? errBody;
            } catch {
              userMessage = errBody || `HTTP ${jobResp.status}`;
            }
            const NON_RETRYABLE = [400, 401, 402, 403, 404];
            if (NON_RETRYABLE.includes(jobResp.status)) {
              throw Object.assign(new Error(userMessage), { nonRetryable: true, code: jobResp.status });
            }
            throw Object.assign(new Error(userMessage), { code: jobResp.status });
          }
        }
      } catch (jobErr: any) {
        if (useLegacyStream) {
          response = await fetch(`${AI_API_URL}/api/generate/pipeline/stream`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
            body: JSON.stringify({
              job_title: jobTitle,
              company: company || "",
              jd_text: jdText,
              resume_text: resumeText,
            }),
            signal: controller.signal,
          });
        } else {
          throw jobErr;
        }
      }

      if (!response) throw new Error("No AI response stream");

      if (!response.ok) {
        clearTimeout(hardTimeout);
        const errBody = await response.text().catch(() => "");
        let userMessage: string;
        try {
          const parsed = JSON.parse(errBody);
          userMessage = parsed.detail ?? errBody;
        } catch {
          userMessage = errBody || `HTTP ${response.status}`;
        }
        const retryAfterHeader = response.headers.get("Retry-After");
        const retryAfterSeconds = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined;
        const NON_RETRYABLE = [400, 401, 402, 403, 404, 499];
        if (NON_RETRYABLE.includes(response.status)) {
          throw Object.assign(new Error(userMessage), {
            nonRetryable: true,
            code: response.status,
            retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : undefined,
          });
        }
        throw Object.assign(new Error(userMessage), {
          code: response.status,
          retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : undefined,
        });
      }

      // ── Parse SSE stream ──────────────────────────────────────────
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Streaming not supported by browser");

      const decoder = new TextDecoder();
      let buffer = "";
      let result: any = null;
      let streamError: string | null = null;

      // Inactivity timeout: if no bytes arrive for a while, something is stuck
      let inactivityTimer: ReturnType<typeof setTimeout> | null = null;
      // Configurable via NEXT_PUBLIC_AI_INACTIVITY_TIMEOUT_MS.
      const inactivityMsRaw = Number.parseInt(process.env.NEXT_PUBLIC_AI_INACTIVITY_TIMEOUT_MS ?? "", 10);
      const inactivityMs = Number.isFinite(inactivityMsRaw) && inactivityMsRaw > 0 ? inactivityMsRaw : 120_000;
      const resetInactivity = () => {
        if (inactivityTimer) clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(() => {
          abortedBy = abortedBy ?? "inactivity";
          controller.abort();
        }, inactivityMs);
      };
      resetInactivity();

      // Allow callers (wizard UI) to cancel without waiting for inactivity/hard timeouts.
      const externalSignal = opts?.signal;
      const onExternalAbort = () => {
        abortedBy = abortedBy ?? "user";
        // Propagate cancel to the backend job runner (so it stops burning quota).
        void cancelJobBestEffort();
        controller.abort();
      };
      if (externalSignal) {
        if (externalSignal.aborted) {
          onExternalAbort();
        } else {
          externalSignal.addEventListener("abort", onExternalAbort, { once: true });
        }
      }

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          resetInactivity();
          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          let currentEvent = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              const dataStr = line.slice(6);
              try {
                const data = JSON.parse(dataStr);

                if (currentEvent === "progress") {
                  onProgress?.(data as PipelineProgress);
                } else if (currentEvent === "agent_status") {
                  opts?.onAgentEvent?.(data as PipelineAgentEvent);
                } else if (currentEvent === "detail") {
                  opts?.onDetailEvent?.(data as PipelineDetailEvent);
                } else if (currentEvent === "complete") {
                  result = data.result;
                  onProgress?.({
                    phase: "complete",
                    step: data.result ? 6 : 0,
                    totalSteps: 6,
                    progress: 100,
                    message: "All done!",
                  });
                } else if (currentEvent === "error") {
                  streamError = data.message || "AI generation failed";
                  const code = data.code || 500;
                  const retryAfterSeconds = data.retryAfterSeconds ?? data.retry_after_seconds ?? data.retryAfter ?? undefined;
                  const NON_RETRYABLE_CODES = [400, 401, 402, 403, 404, 499];
                  if (NON_RETRYABLE_CODES.includes(code)) {
                    throw Object.assign(new Error(streamError ?? "AI generation failed"), {
                      nonRetryable: true,
                      code,
                      retryAfterSeconds,
                    });
                  }
                  throw Object.assign(new Error(streamError ?? "AI generation failed"), {
                    code,
                    retryAfterSeconds,
                  });
                }
              } catch (parseErr: any) {
                if (parseErr.nonRetryable) throw parseErr;
                if (parseErr.message === streamError) throw parseErr;
                console.warn("[HireStack] SSE parse error:", parseErr);
              }
              currentEvent = "";
            }
          }
        }
      } finally {
        if (externalSignal) externalSignal.removeEventListener("abort", onExternalAbort);
        if (inactivityTimer) clearTimeout(inactivityTimer);
        clearTimeout(hardTimeout);
        reader.releaseLock();
      }

      if (!result) {
        throw new Error("AI pipeline stream ended without producing results");
      }

      // ── Sanity-check results and apply deterministic fallbacks ────
      // When cloud providers are rate-limited, local models can occasionally
      // return sparse/empty module payloads. Fill them from the confirmed
      // facts to keep the workspace usable and avoid "Ready" modules with no content.
      const keywords: string[] = Array.isArray(result?.benchmark?.keywords) && result.benchmark.keywords.length > 0
        ? (result.benchmark.keywords as any[]).filter((k) => typeof k === "string")
        : extractKeywords(jdText, 25);

      const shouldReplaceBenchmark = !result?.benchmark
        || !Array.isArray(result.benchmark.keywords)
        || result.benchmark.keywords.length === 0
        || !Array.isArray(result.benchmark.rubric)
        || result.benchmark.rubric.length === 0;
      if (shouldReplaceBenchmark) {
        result.benchmark = {
          ...(result.benchmark ?? {}),
          ...buildBenchmark(jobTitle, company || undefined, keywords),
        };
      }

      const isGapsEmpty = !result?.gaps
        || (!Array.isArray(result.gaps.missingKeywords) || result.gaps.missingKeywords.length === 0)
        && (!Array.isArray(result.gaps.strengths) || result.gaps.strengths.length === 0)
        && (!Array.isArray(result.gaps.recommendations) || result.gaps.recommendations.length === 0);
      if (isGapsEmpty) {
        result.gaps = {
          ...(result.gaps ?? {}),
          ...buildGaps(confirmedFacts, keywords),
          createdAt: Date.now(),
        };
      }

      const missingKeywords = Array.isArray(result?.gaps?.missingKeywords) ? result.gaps.missingKeywords : [];
      const shouldReplaceLearningPlan = !result?.learningPlan
        || !Array.isArray(result.learningPlan.plan)
        || result.learningPlan.plan.length === 0;
      if (shouldReplaceLearningPlan) {
        result.learningPlan = {
          ...(result.learningPlan ?? {}),
          ...buildLearningPlan(missingKeywords.length > 0 ? missingKeywords : keywords.slice(0, 8)),
          createdAt: Date.now(),
        };
      }

      if (!String(result.cvHtml ?? "").trim()) {
        result.cvHtml = seedCvHtml(confirmedFacts, jobTitle, company || undefined, keywords, resumeText);
      }
      if (!String(result.coverLetterHtml ?? "").trim()) {
        result.coverLetterHtml = seedCoverLetterHtml(confirmedFacts, jobTitle, company || undefined, keywords);
      }
      if (!String(result.personalStatementHtml ?? "").trim()) {
        result.personalStatementHtml = seedPersonalStatementHtml(
          confirmedFacts,
          jobTitle,
          company || undefined,
          keywords,
          resumeText
        );
      }
      if (!String(result.portfolioHtml ?? "").trim()) {
        result.portfolioHtml = seedPortfolioHtml(
          confirmedFacts,
          jobTitle,
          company || undefined,
          keywords,
          resumeText
        );
      }

      // Validate that we got at least something meaningful back
      if (!String(result.cvHtml ?? "").trim() && !result.benchmark && !result.gaps) {
        throw new Error("AI pipeline returned empty results");
      }

      if (!serverOwnsPersistence) {
        const patch: Record<string, any> = {};
        const requested = new Set(modules);

        if (requested.has("benchmark") && result.benchmark) {
          patch.benchmark = { ...result.benchmark, createdAt: Date.now() };
        }
        if (requested.has("gaps") && result.gaps) patch.gaps = result.gaps;
        if (requested.has("learningPlan") && result.learningPlan) patch.learningPlan = result.learningPlan;
        if (requested.has("cv") && result.cvHtml) patch.cvHtml = result.cvHtml;
        if (requested.has("coverLetter") && result.coverLetterHtml) patch.coverLetterHtml = result.coverLetterHtml;
        if (requested.has("personalStatement") && result.personalStatementHtml) patch.personalStatementHtml = result.personalStatementHtml;
        if (requested.has("portfolio") && result.portfolioHtml) patch.portfolioHtml = result.portfolioHtml;
        if (requested.has("scorecard")) {
          if (result.validation) patch.validation = result.validation;
          if (result.scorecard) patch.scorecard = { ...result.scorecard, updatedAt: Date.now() };
          if (result.scores) patch.scores = result.scores;
        }

        if (result.discoveredDocuments) {
          (patch as any).discovered_documents = result.discoveredDocuments;
        }
        if (result.generatedDocuments) {
          (patch as any).generated_documents = result.generatedDocuments;
        }
        if (result.benchmarkDocuments) {
          (patch as any).benchmark_documents = result.benchmarkDocuments;
        }
        if (result.documentStrategy) {
          (patch as any).document_strategy = result.documentStrategy;
        }
        if (result.companyIntel) {
          (patch as any).company_intel = result.companyIntel;
        }

        const readyAt = Date.now();
        for (const mod of modules) {
          moduleStates[mod] = { state: "ready", updatedAt: readyAt };
        }
        patch.modules = moduleStates;

        await patchApplication(appId, patch);
        if (requested.has("gaps") || requested.has("learningPlan")) {
          try {
            await syncAutoTasks(
              appId,
              userId,
              requested.has("gaps") ? result.gaps : undefined,
              requested.has("learningPlan") ? result.learningPlan : undefined
            );
          } catch (taskErr) {
            console.warn("[HireStack] Task sync failed:", (taskErr as any)?.message ?? taskErr);
          }
        }
      }
      console.log("[HireStack] AI pipeline succeeded on attempt", attempt);
      return; // Success
    } catch (apiError: any) {
      lastError = apiError;

      if (apiError.name === "AbortError") {
        if (abortedBy === "user") {
          if (usedJobApi) cancelledByUserViaJob = true;
          apiError.nonRetryable = true;
          lastError = new Error("Generation cancelled.");
        } else if (abortedBy === "inactivity") {
          lastError = new Error("Generation appears stuck (no progress). Please try again.");
        } else {
          lastError = new Error("Generation timed out — the AI took too long. Please try again.");
        }
      }

      console.warn(`[HireStack] AI pipeline attempt ${attempt} failed:`, lastError!.message);

      if (apiError.nonRetryable) break;
      if (attempt < MAX_RETRIES) {
        const retryAfterSeconds = Number(apiError?.retryAfterSeconds);
        const delayMs = Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
          ? retryAfterSeconds * 1000
          : attempt * 2000;
        if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0) {
          onProgress?.({
            phase: "rate_limited",
            step: 0,
            totalSteps: 6,
            progress: 5,
            message: `AI rate limited — retrying in ${retryAfterSeconds}s…`,
          });
        }
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }
  }

  // All retries failed
  console.error("[HireStack] AI pipeline failed after all retries:", lastError?.message);

  const baseErrorMessage = (lastError?.message ?? "AI generation failed").trim();
  if (cancelledByUserViaJob && baseErrorMessage.toLowerCase().includes("cancel")) {
    // Job-based cancellation restores module states server-side; don't overwrite.
    throw new Error("Generation cancelled.");
  }
  if (serverOwnsPersistence) {
    throw new Error(lastError?.message ?? "AI generation failed. Please try again.");
  }
  const needsPunctuation = !/[.!?]$/.test(baseErrorMessage);
  const moduleErrorMessage = `${baseErrorMessage}${needsPunctuation ? "." : ""} Click Regenerate to retry.`;

  const errorAt = Date.now();
  for (const mod of modules) {
    moduleStates[mod] = { state: "error", error: moduleErrorMessage, updatedAt: errorAt };
  }
  const { error: errorSetErr } = await supabase
    .from(TABLES.applications)
    .update({ modules: moduleStates })
    .eq("id", appId);
  if (errorSetErr) throw errorSetErr;

  throw new Error(lastError?.message ?? "AI generation failed. Please try again.");
}

/**
 * Local/offline builder fallback — used when the AI backend is unavailable.
 */
async function generateWithLocalBuilders(
  appId: string,
  userId: string,
  confirmedFacts: ConfirmedFacts,
  modules: ModuleKey[]
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
/*  ON-DEMAND OPTIONAL DOCUMENT GENERATION                              */
/* ================================================================== */

export async function generateOptionalDocument(
  applicationId: string,
  docKey: string,
  docLabel: string = "",
): Promise<{ doc_key: string; doc_label: string; html: string }> {
  const { error: userErr } = await supabase.auth.getUser();
  if (userErr) throw new Error("Authentication required");
  const { data: sessionData } = await supabase.auth.getSession();
  const accessToken = sessionData.session?.access_token ?? null;
  if (!accessToken) throw new Error("Authentication required");

  const res = await fetch(`${AI_API_URL}/api/generate/document`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      application_id: applicationId,
      doc_key: docKey,
      doc_label: docLabel,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to generate document (${res.status})`);
  }

  return res.json();
}

/* ================================================================== */
/*  DOC VERSIONING                                                      */
/* ================================================================== */

export async function snapshotDocVersion(
  appId: string,
  docType: "cv" | "coverLetter" | "personalStatement" | "portfolio",
  labelOrHtml?: string,
  label?: string
): Promise<void> {
  const versionId = uid("ver");
  const colKeyMap: Record<string, string> = {
    cv: "cv_versions",
    coverLetter: "cl_versions",
    personalStatement: "ps_versions",
    portfolio: "portfolio_versions",
  };
  const htmlColKeyMap: Record<string, string> = {
    cv: "cv_html",
    coverLetter: "cover_letter_html",
    personalStatement: "personal_statement_html",
    portfolio: "portfolio_html",
  };
  const colKey = colKeyMap[docType] || "cv_versions";
  const htmlColKey = htmlColKeyMap[docType] || "cv_html";

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
  docType: "cv" | "coverLetter" | "personalStatement" | "portfolio",
  versionId: string
): Promise<void> {
  const colKeyMap: Record<string, string> = {
    cv: "cv_versions",
    coverLetter: "cl_versions",
    personalStatement: "ps_versions",
    portfolio: "portfolio_versions",
  };
  const htmlKeyMap: Record<string, string> = {
    cv: "cv_html",
    coverLetter: "cover_letter_html",
    personalStatement: "personal_statement_html",
    portfolio: "portfolio_html",
  };
  const colKey = colKeyMap[docType] || "cv_versions";
  const htmlKey = htmlKeyMap[docType] || "cv_html";

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
  if (task.detail !== undefined) row.detail = task.detail;
  if (task.why !== undefined) row.why = task.why;
  if (task.status !== undefined) row.status = task.status;
  if (task.priority !== undefined) row.priority = task.priority;
  if (task.dueDate !== undefined) row.due_date = task.dueDate ? new Date(task.dueDate).toISOString() : null;

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

  // Buckets are private by default; store a stable storage reference and
  // resolve to a signed URL only when the user opens/downloads the file.
  return `storage://${bucket}/${path}`;
}

export async function uploadResume(
  userId: string,
  file: File
): Promise<string> {
  const ext = file.name.split(".").pop() ?? "pdf";
  const path = `${userId}/resumes/${uid("resume")}.${ext}`;
  return uploadFile("uploads", path, file);
}

/**
 * Server-side resume parsing (PDF/DOCX/TXT) for reliable text extraction.
 * Uses the backend `/api/resume/parse` endpoint (Supabase JWT auth).
 */
export async function parseResumeText(
  file: File,
  maxPages: number = 4
): Promise<string> {
  const { data: sessionData, error: sessionErr } = await supabase.auth.getSession();
  if (sessionErr) throw sessionErr;
  const accessToken = sessionData.session?.access_token;
  if (!accessToken) throw new Error("Not authenticated. Please sign in again.");

  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${AI_API_URL}/api/resume/parse?max_pages=${maxPages}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: form,
  });

  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    let userMessage = errBody || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(errBody);
      userMessage = parsed.detail ?? userMessage;
    } catch {
      // ignore
    }
    throw new Error(userMessage);
  }

  const data = await res.json().catch(() => ({}));
  return String(data?.text ?? "").trim();
}

export async function uploadEvidenceFile(
  userId: string,
  file: File
): Promise<string> {
  const ext = file.name.split(".").pop() ?? "pdf";
  const path = `${userId}/evidence/${uid("file")}.${ext}`;
  return uploadFile("uploads", path, file);
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

export function computeEvidenceStrengthScore(input: {
  evidence: EvidenceDoc[];
  keywords: string[];
}): number {
  const norm = (s: string) =>
    String(s ?? "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .replace(/\s+/g, " ");

  const keywordsNorm = Array.from(
    new Set(
      (input.keywords ?? [])
        .filter((k) => typeof k === "string")
        .map((k) => norm(k))
        .filter(Boolean)
    )
  );
  if (keywordsNorm.length === 0) return 0;

  const evidenceText = norm(
    (input.evidence ?? [])
      .map((e) =>
        [
          e.title,
          e.description,
          ...(Array.isArray(e.skills) ? e.skills : []),
          ...(Array.isArray(e.tools) ? e.tools : []),
          ...(Array.isArray(e.tags) ? e.tags : []),
        ]
          .filter(Boolean)
          .join(" ")
      )
      .join(" ")
  );
  if (!evidenceText) return 0;

  const haystack = ` ${evidenceText} `;
  let covered = 0;
  for (const kw of keywordsNorm) {
    const needle = ` ${kw} `;
    if (haystack.includes(needle)) {
      covered += 1;
      continue;
    }
    // Allow substring matches for longer keywords (handles e.g. "tailwind" inside "tailwindcss").
    if (kw.length >= 4 && haystack.includes(kw)) {
      covered += 1;
    }
  }

  const score = Math.round((covered / keywordsNorm.length) * 100);
  return Math.max(0, Math.min(100, score));
}

/* ================================================================== */
/*  COACH ACTIONS                                                       */
/* ================================================================== */

export type CoachActionKind = "fix" | "write" | "collect" | "review" | "danger" | "replay";

export interface CoachAction {
  kind: CoachActionKind;
  title: string;
  why: string;
  cta: string;
  signal?: string;
}

export function buildCoachActions(ctx: {
  missingKeywords: string[];
  factsLocked: boolean;
  evidenceCount: number;
  /** v7: runtime truth signals from agent pipeline */
  fabricatedClaims?: number;
  unsupportedClaims?: number;
  validationHardFailures?: number;
  validationSoftWarnings?: number;
  residualMissingKeywords?: string[];
  replayFailureClass?: string | null;
  contradictionCount?: number;
  finalATSScore?: number | null;
}): CoachAction[] {
  const actions: CoachAction[] = [];

  // Priority 0: unlock facts — nothing else matters until facts are confirmed
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

  // Priority 1: fabricated claims — immediate danger to application credibility
  if ((ctx.fabricatedClaims ?? 0) > 0) {
    actions.push({
      kind: "danger",
      title: `Remove ${ctx.fabricatedClaims} fabricated claim${ctx.fabricatedClaims !== 1 ? "s" : ""}`,
      why: "The fact-checker flagged claims as fabricated. These undermine your entire application and can fail ATS screening.",
      cta: "Review claims",
      signal: "fact_checker.fabricated",
    });
  }

  // Priority 2: validation hard failures — document won't pass quality gate
  if ((ctx.validationHardFailures ?? 0) > 0) {
    actions.push({
      kind: "danger",
      title: `Fix ${ctx.validationHardFailures} validation failure${ctx.validationHardFailures !== 1 ? "s" : ""}`,
      why: "The validator found blocking issues that must be resolved before export.",
      cta: "View issues",
      signal: "validator.hard_failure",
    });
  }

  // Priority 3: unsupported claims — weaken evidence chain
  if ((ctx.unsupportedClaims ?? 0) > 0) {
    actions.push({
      kind: "fix",
      title: `Back up ${ctx.unsupportedClaims} unsupported claim${ctx.unsupportedClaims !== 1 ? "s" : ""}`,
      why: "Claims without linked evidence weaken your application. Add projects or certificates to support them.",
      cta: "Add evidence",
      signal: "evidence_inspector.unsupported",
    });
  }

  // Priority 4: replay failure — if the last generation failed, explain why
  if (ctx.replayFailureClass && ctx.replayFailureClass !== "unknown") {
    actions.push({
      kind: "replay",
      title: "Review generation failure",
      why: `The last generation failed (${ctx.replayFailureClass.replace(/_/g, " ")}). Review the replay analysis to understand what went wrong.`,
      cta: "View replay",
      signal: `replay.${ctx.replayFailureClass}`,
    });
  }

  // Priority 5: no evidence at all
  if (ctx.evidenceCount === 0) {
    actions.push({
      kind: "collect",
      title: "Collect evidence",
      why: "Upload certificates, project links, or other proof to strengthen your application.",
      cta: "Open vault",
    });
  }

  // Priority 6: residual missing keywords from final analysis (more precise than gap analysis)
  const residualMissing = ctx.residualMissingKeywords ?? ctx.missingKeywords;
  if (residualMissing.length > 0 && actions.length < 3) {
    actions.push({
      kind: "fix",
      title: `Add proof for ${residualMissing[0]}`,
      why: residualMissing.length > 1
        ? `${residualMissing.length} keywords still missing after optimization: ${residualMissing.slice(0, 3).join(", ")}${residualMissing.length > 3 ? "…" : ""}.`
        : `You're missing evidence for ${residualMissing[0]}. Add a project or cert.`,
      cta: "Fix in CV",
      signal: residualMissing === ctx.residualMissingKeywords ? "final_analysis.missing_keywords" : "gap_analysis.missing",
    });
  }

  // Priority 7: contradictions
  if ((ctx.contradictionCount ?? 0) > 0 && actions.length < 3) {
    actions.push({
      kind: "fix",
      title: `Resolve ${ctx.contradictionCount} contradiction${ctx.contradictionCount !== 1 ? "s" : ""}`,
      why: "Contradictory information was detected between your claims and evidence.",
      cta: "Review evidence",
      signal: "evidence_inspector.contradiction",
    });
  }

  // Priority 8: low ATS score after optimization
  if (ctx.finalATSScore != null && ctx.finalATSScore < 75 && actions.length < 3) {
    actions.push({
      kind: "fix",
      title: `Improve ATS score (${ctx.finalATSScore}/100)`,
      why: "Your ATS score is below the 75% target. Add missing keywords and rephrase content to improve machine readability.",
      cta: "View ATS",
      signal: "final_analysis.low_ats",
    });
  }

  // Default: everything looks good
  if (actions.length === 0) {
    actions.push({
      kind: "write",
      title: "Take a snapshot",
      why: "All modules look good. Snapshot your CV and cover letter versions.",
      cta: "Open versions",
    });
  }

  return actions;
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

function extractResumeHighlights(resumeText: string, max = 6): string[] {
  const lines = String(resumeText ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const bullets = lines
    .filter((l) => /^[-•]\s+/.test(l))
    .map((l) => l.replace(/^[-•]\s+/, "").trim())
    .filter(Boolean);

  // If there are no bullets, fall back to a few short lines near the top.
  const fallback = lines
    .slice(0, 12)
    .filter((l) => l.length >= 12 && l.length <= 140 && !/^https?:\/\//.test(l));

  const picks = bullets.length > 0 ? bullets : fallback;
  return picks.slice(0, max);
}

export function seedPersonalStatementHtml(
  facts: ConfirmedFacts,
  jobTitle: string,
  company: string | undefined,
  keywords: string[],
  resumeText: string
): string {
  const companyStr = company || "the company";
  const resumeName = facts?.resume?.name;
  const highlights = extractResumeHighlights(resumeText, 5);
  const kw = (keywords ?? []).filter((k) => typeof k === "string" && k.trim()).slice(0, 6);

  const parts: string[] = [];
  parts.push("<h2>Personal Statement</h2>");
  parts.push(
    `<p>I’m applying for the <strong>${jobTitle}</strong> role at <strong>${companyStr}</strong>. I focus on proof-backed work: clear outcomes, measurable impact, and artifacts that make claims credible.</p>`
  );
  if (resumeName) {
    parts.push(`<p><strong>Resume:</strong> ${resumeName}</p>`);
  }

  if (highlights.length > 0) {
    parts.push("<p><strong>Highlights from my resume:</strong></p>");
    parts.push("<ul>");
    for (const h of highlights) parts.push(`<li>${h}</li>`);
    parts.push("</ul>");
  }

  if (kw.length > 0) {
    parts.push(
      `<p>For this role, I’m emphasizing <strong>${kw.join(", ")}</strong> and making sure each key keyword is supported by evidence in my vault.</p>`
    );
  }

  parts.push(
    "<p>I’m excited to bring this approach to your team and deliver value quickly through thoughtful execution, collaboration, and a relentless focus on user outcomes.</p>"
  );

  return parts.join("");
}

export function seedPortfolioHtml(
  facts: ConfirmedFacts,
  jobTitle: string,
  company: string | undefined,
  keywords: string[],
  resumeText: string
): string {
  const companyStr = company || "the company";
  const resumeName = facts?.resume?.name;
  const highlights = extractResumeHighlights(resumeText, 4);
  const kw = (keywords ?? []).filter((k) => typeof k === "string" && k.trim()).slice(0, 8);

  const parts: string[] = [];
  parts.push("<h2>Portfolio & Evidence</h2>");
  parts.push(`<p>Proof-first checklist for <strong>${jobTitle}</strong> at <strong>${companyStr}</strong>. Attach links/files in Evidence and reference them in your docs.</p>`);
  if (resumeName) {
    parts.push(`<p><strong>Resume:</strong> ${resumeName}</p>`);
  }

  if (highlights.length > 0) {
    parts.push("<p><strong>Resume proof hooks:</strong></p>");
    parts.push("<ul>");
    for (const h of highlights) parts.push(`<li>${h}</li>`);
    parts.push("</ul>");
  }

  if (kw.length > 0) {
    parts.push("<p><strong>Priority proof targets:</strong></p>");
    parts.push("<ul>");
    for (const k of kw) {
      parts.push(
        `<li><strong>${k}</strong> — Add 1 concrete artifact (project, cert, write-up) that demonstrates this keyword with measurable outcomes.</li>`
      );
    }
    parts.push("</ul>");
  }

  return parts.join("");
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
