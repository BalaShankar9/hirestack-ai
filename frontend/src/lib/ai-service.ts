/**
 * AI Service — Bridge between frontend Firestore data model and backend AI API.
 *
 * Each function creates the needed backend resources on-the-fly, calls the
 * AI chain, and maps back to the frontend ApplicationDoc data model.
 * Falls back gracefully (returns null) so callers can use static templates.
 */
import api from "@/lib/api";
import type {
  BenchmarkModule,
  ConfirmedFacts,
  GapsModule,
  LearningPlanModule,
} from "@/lib/firestore/models";

const AI_ENABLED =
  typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_AI_ENABLED !== "false"
    : true;

/* ---------- Shared session state for a single generation run ---------- */

/**
 * Holds backend resource IDs created during a single generation run so
 * subsequent AI calls can reference them without redundant creation.
 */
export interface AISession {
  backendJobId?: string;
  backendProfileId?: string;
  backendBenchmarkId?: string;
  backendGapReportId?: string;
}

let _session: AISession = {};

/** Reset session — call at the start of each generation run. */
export function resetAISession() {
  _session = {};
}

/** Get current session for inspection / debugging. */
export function getAISession(): Readonly<AISession> {
  return { ..._session };
}

/* ---------- Helper: ensure a backend job exists ---------- */

async function ensureBackendJob(
  jobTitle: string,
  company: string | undefined,
  jobDescription: string,
  keywords: string[],
): Promise<string> {
  if (_session.backendJobId) return _session.backendJobId;

  const job = await api.createJob({
    title: jobTitle,
    company: company || "",
    description: jobDescription || keywords.join(", "),
    raw_text: jobDescription || "",
  });
  _session.backendJobId = job.id;
  return job.id;
}

/* ---------- Helper: ensure a backend profile exists ---------- */

async function ensureBackendProfile(
  confirmed: ConfirmedFacts | null,
): Promise<string | undefined> {
  if (_session.backendProfileId) return _session.backendProfileId;

  // Try to fetch the user's primary profile from the backend
  try {
    const profile = await api.getPrimaryProfile();
    if (profile?.id) {
      _session.backendProfileId = profile.id;
      return profile.id;
    }
  } catch {
    // No profile uploaded yet — AI gap/doc analysis will fall back to template
  }
  return undefined;
}

/* ---------- Public AI functions ---------- */

/**
 * Call backend AI to generate benchmark. Returns null if API unavailable.
 */
export async function aiBuildBenchmark(
  jobTitle: string,
  company: string | undefined,
  keywords: string[],
  jobDescription?: string,
): Promise<BenchmarkModule | null> {
  if (!AI_ENABLED) return null;

  try {
    const jobId = await ensureBackendJob(
      jobTitle,
      company,
      jobDescription || "",
      keywords,
    );

    const benchmark = await api.generateBenchmark(jobId);
    _session.backendBenchmarkId = benchmark.id;

    return {
      summary: benchmark.ideal_profile_summary || benchmark.summary || "",
      keywords: benchmark.key_skills || keywords,
      rubric: benchmark.rubric || [],
      createdAt: Date.now(),
    };
  } catch (e) {
    console.warn("[AI] Benchmark generation failed, falling back to template:", e);
    return null;
  }
}

/**
 * Call backend AI to analyze gaps.
 */
export async function aiAnalyzeGaps(
  confirmed: ConfirmedFacts | null,
  keywords: string[],
): Promise<GapsModule | null> {
  if (!AI_ENABLED) return null;

  try {
    const profileId = await ensureBackendProfile(confirmed);
    const benchmarkId = _session.backendBenchmarkId;

    if (!profileId || !benchmarkId) return null;

    const report = await api.analyzeGaps(profileId, benchmarkId);
    _session.backendGapReportId = report.id;

    return {
      missingKeywords: report.missing_skills || report.missingKeywords || [],
      strengths: report.strengths || [],
      recommendations: report.recommendations || [],
      createdAt: Date.now(),
    };
  } catch (e) {
    console.warn("[AI] Gap analysis failed, falling back to template:", e);
    return null;
  }
}

/**
 * Call backend AI to generate a learning plan / roadmap.
 */
export async function aiBuildLearningPlan(
  missingKeywords: string[],
): Promise<LearningPlanModule | null> {
  if (!AI_ENABLED) return null;

  try {
    const gapReportId = _session.backendGapReportId;
    if (!gapReportId) return null;

    const roadmap = await api.generateRoadmap(gapReportId, "Learning Plan");
    const milestones = roadmap.milestones || [];

    const plan = milestones.map((m: any, i: number) => ({
      week: i + 1,
      theme: m.title || `Week ${i + 1}`,
      outcomes: m.outcomes || [],
      tasks: m.tasks || [],
    }));

    return {
      focus: missingKeywords.slice(0, 4),
      plan,
      resources: (roadmap.resources || []).map((r: any) => ({
        title: r.title || "",
        provider: r.provider || "HireStack Coach",
        timebox: r.timebox || "60-90 min",
        skill: r.skill || "",
      })),
      createdAt: Date.now(),
    };
  } catch (e) {
    console.warn("[AI] Learning plan generation failed, falling back to template:", e);
    return null;
  }
}

/**
 * Call backend AI to generate a tailored CV.
 */
export async function aiGenerateCv(): Promise<string | null> {
  if (!AI_ENABLED) return null;

  try {
    const profileId = _session.backendProfileId;
    const jobId = _session.backendJobId;
    if (!profileId || !jobId) return null;

    const doc = await api.generateDocument({
      document_type: "cv",
      profile_id: profileId,
      job_id: jobId,
      benchmark_id: _session.backendBenchmarkId,
    });
    return doc.content || null;
  } catch (e) {
    console.warn("[AI] CV generation failed, falling back to template:", e);
    return null;
  }
}

/**
 * Call backend AI to generate a cover letter.
 */
export async function aiGenerateCoverLetter(): Promise<string | null> {
  if (!AI_ENABLED) return null;

  try {
    const profileId = _session.backendProfileId;
    const jobId = _session.backendJobId;
    if (!profileId || !jobId) return null;

    const doc = await api.generateDocument({
      document_type: "cover_letter",
      profile_id: profileId,
      job_id: jobId,
      benchmark_id: _session.backendBenchmarkId,
    });
    return doc.content || null;
  } catch (e) {
    console.warn("[AI] Cover letter generation failed, falling back to template:", e);
    return null;
  }
}

