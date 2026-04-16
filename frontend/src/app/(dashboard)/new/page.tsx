"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CheckCircle2,
  FileText,
  Fingerprint,
  Loader2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { PipelineAgentView } from "@/components/pipeline/pipeline-agent-view";

import { useAuth } from "@/components/providers";
import {
  cancelGenerationJob,
  createApplication,
  generateApplicationModules,
  patchApplication,
  parseResumeText,
  uploadResume,
  computeJDQuality,
  extractKeywords,
  trackEvent,
} from "@/lib/firestore/ops";
import { useGenerationJob, useGenerationJobEvents } from "@/lib/firestore/hooks";
import type { PipelineAgentEvent, PipelineDetailEvent, PipelineProgress } from "@/lib/firestore/ops";
import type { ConfirmedFacts, GenerationJobEventDoc, JDQuality, ResumeArtifact } from "@/lib/firestore/models";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { UploadZone } from "@/components/upload-zone";
import { toast } from "@/hooks/use-toast";
import api from "@/lib/api";
import type { Profile } from "@/types";

/* ------------------------------------------------------------------ */
/*  Steps                                                               */
/* ------------------------------------------------------------------ */

type Step = "job" | "resume" | "review" | "generate";

const STEPS: { key: Step; label: string; icon: any }[] = [
  { key: "job", label: "Job Description", icon: Briefcase },
  { key: "resume", label: "Upload Resume", icon: FileText },
  { key: "review", label: "Review Facts", icon: CheckCircle2 },
  { key: "generate", label: "Generate", icon: Sparkles },
];

const PROGRESS_PHASE_TO_INDEX: Record<string, number> = {
  initializing: 0,
  recon: 0,
  recon_done: 0,
  profiling: 1,
  profiling_done: 1,
  gap_analysis: 2,
  gap_analysis_done: 2,
  documents: 3,
  documents_done: 3,
  portfolio: 4,
  portfolio_done: 4,
  validation: 5,
  validation_done: 5,
  formatting: 6,
  complete: 6,
};

const PIPELINE_TO_INDEX: Record<string, number> = {
  recon: 0,
  resume_parse: 1,
  benchmark: 1,
  gap_analysis: 2,
  cv_generation: 3,
  cover_letter: 3,
  career_roadmap: 3,
  personal_statement: 4,
  portfolio: 4,
  validation: 5,
  pipeline: 6,
};

function getPhaseIndexFromProgress(phase: string): number {
  return PROGRESS_PHASE_TO_INDEX[phase] ?? -1;
}

function getPhaseIndexFromDetail(event: PipelineDetailEvent): number {
  return PIPELINE_TO_INDEX[event.agent] ?? -1;
}

function getPhaseIndexFromAgentEvent(event: PipelineAgentEvent): number {
  return PIPELINE_TO_INDEX[event.pipeline_name] ?? PIPELINE_TO_INDEX[event.stage] ?? -1;
}

function formatDetailLine(event: PipelineDetailEvent): string {
  const source = event.source ? `[${event.source}] ` : "";
  return `${source}${event.message}`;
}

function formatAgentLine(event: PipelineAgentEvent): string {
  if (event.message?.trim()) return event.message.trim();
  const stage = event.stage.replace(/_/g, " ");
  return `${stage} ${event.status}`;
}

const GENERATION_SESSION_KEY = "hirestack_active_generation";
const TOTAL_PHASES = 7;

function resolveStepParam(value: string | null): Step | null {
  if (!value) return null;
  if (value === "1" || value === "job") return "job";
  if (value === "2" || value === "resume") return "resume";
  if (value === "3" || value === "review") return "review";
  if (value === "4" || value === "generate") return "generate";
  return null;
}

function buildCompletedPhases(completedSteps: number, status?: string | null): Set<number> {
  const completedCount = status === "succeeded"
    ? TOTAL_PHASES
    : Math.max(0, Math.min(TOTAL_PHASES, completedSteps));

  return new Set(Array.from({ length: completedCount }, (_, index) => index));
}

function buildPhaseLogsFromEvents(events: GenerationJobEventDoc[]): Record<number, string[]> {
  const logs: Record<number, string[]> = {};

  const append = (phaseIdx: number, line: string) => {
    if (phaseIdx < 0) return;
    const cleaned = line.trim();
    if (!cleaned) return;
    const existing = logs[phaseIdx] || [];
    if (existing[existing.length - 1] === cleaned) return;
    logs[phaseIdx] = [...existing, cleaned].slice(-60);
  };

  for (const event of events) {
    const payload = event.payload ?? {};

    if (event.eventName === "progress") {
      const phase = String(payload.phase ?? event.stage ?? "");
      const message = String(payload.message ?? event.message ?? "");
      append(getPhaseIndexFromProgress(phase), message);
      continue;
    }

    if (event.eventName === "detail") {
      const detailEvent: PipelineDetailEvent = {
        agent: String(payload.agent ?? event.agentName ?? event.stage ?? ""),
        message: String(payload.message ?? event.message ?? ""),
        status: String(payload.status ?? event.status ?? "info"),
        source: typeof payload.source === "string" ? payload.source : event.source,
        url: typeof payload.url === "string" ? payload.url : event.url,
        metadata: payload.metadata && typeof payload.metadata === "object"
          ? (payload.metadata as Record<string, unknown>)
          : undefined,
      };
      append(getPhaseIndexFromDetail(detailEvent), formatDetailLine(detailEvent));
      continue;
    }

    if (event.eventName === "agent_status") {
      const agentEvent: PipelineAgentEvent = {
        pipeline_name: String(payload.pipeline_name ?? event.agentName ?? ""),
        stage: String(payload.stage ?? event.stage ?? "pipeline"),
        status: String(payload.status ?? event.status ?? "updated"),
        latency_ms: Number(payload.latency_ms ?? event.latencyMs ?? 0),
        message: String(payload.message ?? event.message ?? ""),
        timestamp: typeof payload.timestamp === "string" ? payload.timestamp : undefined,
      };
      append(getPhaseIndexFromAgentEvent(agentEvent), formatAgentLine(agentEvent));
      continue;
    }

    if (event.eventName === "error") {
      const agent = String(payload.agent ?? event.agentName ?? event.stage ?? "recon");
      append(PIPELINE_TO_INDEX[agent] ?? getPhaseIndexFromProgress(String(event.stage ?? "")), event.message);
    }
  }

  return logs;
}

/* ------------------------------------------------------------------ */
/*  Page Component                                                      */
/* ------------------------------------------------------------------ */

export default function NewApplicationPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;

  const [step, setStep] = useState<Step>("job");
  const stepIndex = STEPS.findIndex((s) => s.key === step);
  const [draftAppId, setDraftAppId] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Step 1: Job
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jdText, setJdText] = useState("");
  const [jdQuality, setJdQuality] = useState<JDQuality & { issues: string[]; suggestions: string[] } | null>(null);
  const [jdSaveStatus, setJdSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const jdSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Step 2: Resume
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [resumeUrl, setResumeUrl] = useState("");
  const [uploading, setUploading] = useState(false);

  // Profile pre-fill
  const [nexusProfile, setNexusProfile] = useState<Profile | null>(null);
  const [useNexus, setUseNexus] = useState(false);
  const [nexusLoading, setNexusLoading] = useState(true);

  // Fetch primary profile on mount
  React.useEffect(() => {
    if (!userId) { setNexusLoading(false); return; }
    api.profile.get()
      .then((p: Profile) => {
        if (p?.raw_resume_text) {
          setNexusProfile(p);
          setUseNexus(true);
        }
      })
      .catch((e) => console.error("Failed to load nexus profile", e))
      .finally(() => setNexusLoading(false));
  }, [userId]);

  // When toggling nexus on, pre-fill resume text
  React.useEffect(() => {
    if (useNexus && nexusProfile?.raw_resume_text && !resumeFile) {
      setResumeText(nexusProfile.raw_resume_text);
    } else if (!useNexus && !resumeFile) {
      setResumeText("");
    }
  }, [useNexus, nexusProfile, resumeFile]);

  // Step 4: Generate — real-time SSE progress
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [genError, setGenError] = useState<string | null>(null);
  const [genMessage, setGenMessage] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [completedPhases, setCompletedPhases] = useState<Set<number>>(new Set());
  const [activePhaseIdx, setActivePhaseIdx] = useState(-1);
  const [phaseLogs, setPhaseLogs] = useState<Record<number, string[]>>({});
  const restoreRef = useRef(false);
  const redirectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: generationJob } = useGenerationJob(activeJobId);
  const generationJobStatus = generationJob?.status ?? null;
  const isGenerationJobLive = !generationJobStatus || generationJobStatus === "queued" || generationJobStatus === "running";
  const { data: generationEvents = [] } = useGenerationJobEvents(activeJobId, 600, {
    live: isGenerationJobLive,
  });
  const generationJobApplicationId = generationJob?.applicationId ?? null;
  const generationJobCreatedAt = generationJob?.createdAt;
  const generationJobStartedAt = generationJob?.startedAt;
  const generationJobFinishedAt = generationJob?.finishedAt;

  // Derived
  const keywords = useMemo(() => extractKeywords(jdText), [jdText]);

  const appendPhaseLog = useCallback((phaseIdx: number, line: string) => {
    if (phaseIdx < 0) return;
    const cleaned = line.trim();
    if (!cleaned) return;

    setPhaseLogs((prev) => {
      const existing = prev[phaseIdx] || [];
      if (existing[existing.length - 1] === cleaned) return prev;
      return {
        ...prev,
        [phaseIdx]: [...existing, cleaned].slice(-60),
      };
    });
  }, []);

  const persistGenerationSession = useCallback((appId: string | null, jobId: string | null, nextStep: Step) => {
    if (typeof window === "undefined") return;
    if (!appId && !jobId) {
      window.sessionStorage.removeItem(GENERATION_SESSION_KEY);
      return;
    }
    window.sessionStorage.setItem(
      GENERATION_SESSION_KEY,
      JSON.stringify({ appId, jobId, step: nextStep, savedAt: Date.now() })
    );
  }, []);

  const clearGenerationSession = useCallback(() => {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(GENERATION_SESSION_KEY);
  }, []);

  useEffect(() => {
    if (restoreRef.current) return;
    restoreRef.current = true;

    const paramJobTitle = searchParams.get("jobTitle");
    const paramCompany = searchParams.get("company");
    const paramJdText = searchParams.get("jdText");
    const paramStep = resolveStepParam(searchParams.get("step"));
    const paramAppId = searchParams.get("appId");
    const paramJobId = searchParams.get("jobId");

    if (paramJobTitle && !jobTitle) setJobTitle(paramJobTitle);
    if (paramCompany && !company) setCompany(paramCompany);
    if (paramJdText && !jdText) setJdText(paramJdText);

    let stored: { appId?: string; jobId?: string; step?: Step; savedAt?: number } | null = null;
    if (typeof window !== "undefined") {
      try {
        const raw = window.sessionStorage.getItem(GENERATION_SESSION_KEY);
        stored = raw ? JSON.parse(raw) : null;
        // Expire sessions older than 2 hours to avoid ghost IDs
        if (stored?.savedAt && Date.now() - stored.savedAt > 2 * 60 * 60 * 1000) {
          window.sessionStorage.removeItem(GENERATION_SESSION_KEY);
          stored = null;
        }
      } catch {
        stored = null;
      }
    }

    const restoredAppId = paramAppId || stored?.appId || null;
    const restoredJobId = paramJobId || stored?.jobId || null;
    const restoredStep = paramStep || stored?.step || (restoredJobId ? "generate" : null);

    if (restoredAppId) setDraftAppId(restoredAppId);
    if (restoredJobId) setActiveJobId(restoredJobId);
    if (restoredStep) setStep(restoredStep);
  }, [searchParams, jobTitle, company, jdText]);

  useEffect(() => {
    if (step === "generate" && (draftAppId || activeJobId)) {
      persistGenerationSession(draftAppId, activeJobId, step);
    }
  }, [step, draftAppId, activeJobId, persistGenerationSession]);

  useEffect(() => {
    if (!generationJob) return;

    if (!draftAppId) setDraftAppId(generationJob.applicationId);
    if (step !== "generate") setStep("generate");

    setProgress(generationJob.progress);
    setGenMessage(
      generationJob.message
        || (generationJob.status === "succeeded"
          ? "Your application is ready! 🎉"
          : generationJob.status === "cancelled"
          ? "Generation cancelled."
          : "Resuming generation…")
    );
    setCompletedPhases(buildCompletedPhases(generationJob.completedSteps, generationJob.status));
    setActivePhaseIdx(generationJob.status === "succeeded" ? -1 : getPhaseIndexFromProgress(generationJob.phase ?? ""));

    if (generationJob.status === "queued" || generationJob.status === "running") {
      setGenerating(true);
      setGenError(null);
    } else if (generationJob.status === "succeeded") {
      setGenerating(false);
      setGenError(null);
      appendPhaseLog(6, "Final application bundle ready.");
    } else {
      setGenerating(false);
      setGenError(
        generationJob.errorMessage
          || (generationJob.status === "cancelled"
            ? "Generation cancelled."
            : "Generation failed — please try again.")
      );
    }

    persistGenerationSession(generationJob.applicationId, generationJob.id, "generate");
  }, [generationJob, draftAppId, step, appendPhaseLog, persistGenerationSession]);

  useEffect(() => {
    if (!activeJobId) return;
    setPhaseLogs(buildPhaseLogsFromEvents(generationEvents));
  }, [activeJobId, generationEvents]);

  useEffect(() => {
    if (elapsedRef.current) {
      clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }

    if (!generationJob) return;

    const startedAt = generationJobStartedAt ?? generationJobCreatedAt;
    if (!startedAt) {
      setElapsedMs(0);
      return;
    }

    const updateElapsed = () => {
      const endAt = generationJobFinishedAt ?? Date.now();
      setElapsedMs(Math.max(0, endAt - startedAt));
    };

    updateElapsed();

    if (generationJobStatus === "queued" || generationJobStatus === "running") {
      elapsedRef.current = setInterval(updateElapsed, 500);
      return () => {
        if (elapsedRef.current) {
          clearInterval(elapsedRef.current);
          elapsedRef.current = null;
        }
      };
    }
  }, [generationJob, generationJobStatus, generationJobCreatedAt, generationJobStartedAt, generationJobFinishedAt]);

  useEffect(() => {
    if (redirectRef.current) {
      clearTimeout(redirectRef.current);
      redirectRef.current = null;
    }

    if (step !== "generate" || generationJobStatus !== "succeeded" || !generationJobApplicationId) return;

    redirectRef.current = setTimeout(() => {
      clearGenerationSession();
      setActiveJobId(null);
      router.push(`/applications/${generationJobApplicationId}`);
    }, 1000);

    return () => {
      if (redirectRef.current) {
        clearTimeout(redirectRef.current);
        redirectRef.current = null;
      }
    };
  }, [generationJobStatus, generationJobApplicationId, step, clearGenerationSession, router]);

  /* ---- JD analysis ---- */
  const analyzeJD = useCallback(() => {
    const q = computeJDQuality(jdText);
    setJdQuality(q);
  }, [jdText]);

  /* ---- Resume upload ---- */
  const handleResumeUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      setResumeFile(file);

      try {
        // Server-side text extraction (more reliable than client-side pdf.js across browsers)
        const textPromise = parseResumeText(file).catch((err) => {
          console.warn("[HireStack] Resume parsing failed:", err);
          return "";
        });
        // Only upload to storage if authenticated
        const urlPromise = user ? uploadResume(user.uid, file) : Promise.resolve("");
        const [text, url] = await Promise.all([textPromise, urlPromise]);

        // Warn user if parsing returned empty or very short text
        if (!text || text.trim().length < 50) {
          toast({
            title: "Resume extraction incomplete",
            description: "Text extraction may have failed. You can paste your resume text manually below.",
          });
        }

        setResumeText(text);
        setResumeUrl(url);
      } catch (err) {
        console.error("Resume upload failed:", err);
      } finally {
        setUploading(false);
      }
    },
    [user]
  );

  /* ---- Build confirmed facts ---- */
  const confirmedFacts: ConfirmedFacts = useMemo(
    () => ({
      jobTitle,
      company: company || undefined,
      jdText,
      jdQuality: jdQuality ?? { score: 0, flags: [], summary: "" },
      resume: {
        url: resumeUrl || undefined,
        text: resumeText || undefined,
        name: resumeFile?.name,
        size: resumeFile?.size,
        type: resumeFile?.type,
      },
    }),
    [jobTitle, company, jdText, jdQuality, resumeUrl, resumeText, resumeFile]
  );

  /* ---- Generate (SSE-streamed) ---- */
  const handleGenerate = useCallback(async () => {
    // If a previous run is still in-flight, cancel it before starting a new one.
    abortRef.current?.abort();
    clearGenerationSession();
    setActiveJobId(null);
    setGenerating(true);
    setGenError(null);
    setProgress(0);
    setGenMessage("Initializing AI engine…");
    setElapsedMs(0);
    setCompletedPhases(new Set());
    setActivePhaseIdx(0); // Start with Recon (intel agent) as active
    setPhaseLogs({});

    const uid = user?.uid || user?.id;
    if (!uid) {
      setGenError("You must be logged in to create an application.");
      setGenerating(false);
      return;
    }

    // Start elapsed timer
    const startTime = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startTime);
    }, 500);

    const controller = new AbortController();
    abortRef.current = controller;

    let appId = draftAppId;
    let createdJobId: string | null = null;
    try {
      if (!appId) {
        try {
          appId = await createApplication(
            uid,
            jobTitle || "New Application",
            confirmedFacts
          );
        } catch (createErr) {
          setGenError("Failed to create application workspace. Please try again.");
          setGenerating(false);
          return;
        }
        setDraftAppId(appId);
        persistGenerationSession(appId, null, "generate");

        if (user) await trackEvent(uid, "app_created", appId, {
          jobTitle,
          company,
          jdLength: jdText.length,
          hasResume: !!resumeText,
        });
      } else {
        // Keep the existing draft workspace in sync before regenerating.
        await patchApplication(appId, {
          title: jobTitle || "New Application",
          confirmedFacts,
        });
      }

      const handleProgress = (p: PipelineProgress) => {
        setProgress(p.progress);
        setGenMessage(p.message);

        const phaseIdx = getPhaseIndexFromProgress(p.phase);
        if (phaseIdx >= 0) {
          setActivePhaseIdx(phaseIdx);
          appendPhaseLog(phaseIdx, p.message);
        }

        // Mark phases that are done
        if (p.phase.endsWith("_done") || p.phase === "complete") {
          setCompletedPhases((prev) => {
            const next = new Set(prev);
            if (phaseIdx >= 0) next.add(phaseIdx);
            return next;
          });
        }
      };

      const handleDetail = (event: PipelineDetailEvent) => {
        const phaseIdx = getPhaseIndexFromDetail(event);
        if (phaseIdx >= 0 && (event.status === "running" || event.status === "completed")) {
          setActivePhaseIdx(phaseIdx);
        }
        appendPhaseLog(phaseIdx, formatDetailLine(event));
      };

      const handleAgentEvent = (event: PipelineAgentEvent) => {
        const phaseIdx = getPhaseIndexFromAgentEvent(event);
        if (phaseIdx >= 0 && event.status === "running") {
          setActivePhaseIdx(phaseIdx);
        }
        appendPhaseLog(phaseIdx, formatAgentLine(event));
      };

      await generateApplicationModules(appId, uid, confirmedFacts, undefined, handleProgress, {
        signal: controller.signal,
        onDetailEvent: handleDetail,
        onAgentEvent: handleAgentEvent,
        onJobCreated: (jobId) => {
          createdJobId = jobId;
          setActiveJobId(jobId);
          persistGenerationSession(appId!, jobId, "generate");
        },
      });

      // Done!
      setGenerating(false);
      setProgress(100);
      setGenMessage("Your application is ready! 🎉");
      setCompletedPhases(new Set([0, 1, 2, 3, 4, 5, 6]));
      setActivePhaseIdx(-1);
      appendPhaseLog(6, "Final application bundle ready.");

      if (user) await trackEvent(uid, "app_generated", appId);

      // Legacy stream mode has no job lifecycle updates, so redirect directly.
      if (!createdJobId) {
        clearGenerationSession();
        setActiveJobId(null);
        router.push(`/applications/${appId}`);
      }
    } catch (err: any) {
      setGenerating(false);
      let message: string;
      if (err?.name === "AbortError") {
        message = "Generation timed out. The AI took too long — please try again.";
      } else if (err?.code === 429 || err?.message?.includes("trial limit")) {
        message = err?.message || "Free trial limit reached. Create a free account to continue.";
      } else {
        message = err?.message ?? "Generation failed — please try again.";
      }
      appendPhaseLog(activePhaseIdx >= 0 ? activePhaseIdx : 0, message);
      setGenError(message);
    } finally {
      // Clear timer in all exit paths (success, error, abort)
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current);
        elapsedRef.current = null;
      }
      abortRef.current = null;
    }
  }, [activePhaseIdx, appendPhaseLog, user, draftAppId, jobTitle, company, jdText, resumeText, confirmedFacts, clearGenerationSession, persistGenerationSession, router]);

  /* ---- Navigation ---- */
  function canAdvance(): boolean {
    switch (step) {
      case "job":
        return jobTitle.trim().length > 0 && jdText.trim().length > 20;
      case "resume":
        return true; // resume is optional
      case "review":
        return true;
      default:
        return false;
    }
  }

  function nextStep() {
    if (step === "job") {
      analyzeJD();
      setStep("resume");
    } else if (step === "resume") {
      setStep("review");
    } else if (step === "review") {
      setStep("generate");
      handleGenerate();
    }
  }

  function prevStep() {
    if (step === "resume") setStep("job");
    else if (step === "review") setStep("resume");
  }

  /* ------------------------------------------------------------------ */
  /*  Render                                                              */
  /* ------------------------------------------------------------------ */

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-in">
      {/* Stepper */}
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-xs font-medium text-muted-foreground mr-1">
          Step {stepIndex + 1} of {STEPS.length}
        </span>
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const active = i === stepIndex;
          const done = i < stepIndex;
          return (
            <div key={s.key} className="flex items-center gap-2">
              {i > 0 && (
                <div
                  className={`h-0.5 w-6 rounded-full transition-colors ${done ? "bg-primary" : "bg-muted"}`}
                />
              )}
              <div
                className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all ${
                  active
                    ? "bg-primary text-primary-foreground shadow-glow-sm"
                    : done
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{s.label}</span>
              </div>
            </div>
          );
        })}
      </div>

      {step === "job" && (
        <div className="surface-premium rounded-2xl p-6 card-spotlight">
          <h3 className="text-base font-bold">Paste the Job Description</h3>
          <p className="mt-1 text-xs text-muted-foreground">We’ll extract keywords and build a quality signal.</p>
          <div className="mt-5 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="job-title">Job Title</Label>
                <Input
                  id="job-title"
                  className="rounded-xl h-11"
                  placeholder="Senior Frontend Engineer"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="company">Company</Label>
                <Input
                  id="company"
                  className="rounded-xl h-11"
                  placeholder="TechCorp"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="job-description">Job Description</Label>
                <div className="flex items-center gap-2">
                  {jdSaveStatus === "saving" && (
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                      Saving…
                    </span>
                  )}
                  {jdSaveStatus === "saved" && (
                    <span className="text-[11px] text-emerald-500 flex items-center gap-1">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Saved
                    </span>
                  )}
                  <span className={`text-[11px] tabular-nums ${jdText.trim().length > 20 ? "text-muted-foreground" : "text-amber-500"}`}>
                    {jdText.trim().length > 0 ? `${jdText.trim().split(/\s+/).length} words` : ""}
                  </span>
                </div>
              </div>
              <Textarea
                id="job-description"
                rows={12}
                className="rounded-xl"
                placeholder="Paste the full job description here…"
                value={jdText}
                onChange={(e) => {
                  setJdText(e.target.value);
                  setJdSaveStatus("saving");
                  if (jdSaveTimerRef.current) clearTimeout(jdSaveTimerRef.current);
                  jdSaveTimerRef.current = setTimeout(() => {
                    setJdSaveStatus("saved");
                    setTimeout(() => setJdSaveStatus("idle"), 2500);
                  }, 900);
                }}
              />
              {jdText.trim().length > 0 && jdText.trim().length <= 20 && (
                <p className="text-[11px] text-amber-500">Add more detail — a full JD produces much better results.</p>
              )}
            </div>

            {keywords.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  Detected Keywords ({keywords.length})
                </p>
                <div className="flex flex-wrap gap-1">
                  {keywords.slice(0, 20).map((kw) => (
                    <Badge key={kw} variant="secondary" className="text-xs rounded-lg">
                      {kw}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {step === "resume" && (
        <div className="surface-premium rounded-2xl p-6 card-spotlight">
          <h3 className="text-base font-bold">Upload Your Resume</h3>
          <p className="mt-1 text-xs text-muted-foreground">Optional but helps generate more accurate analysis.</p>
          <div className="mt-5 space-y-4">
            {/* Profile pre-fill */}
            {!nexusLoading && nexusProfile && (
              <button
                type="button"
                onClick={() => {
                  setUseNexus(!useNexus);
                  if (!useNexus) {
                    setResumeFile(null);
                    setResumeUrl("");
                  }
                }}
                className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-all ${
                  useNexus
                    ? "border-teal-500/40 bg-teal-500/5"
                    : "border-border hover:border-teal-500/20"
                }`}
              >
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                  useNexus ? "bg-teal-500/15" : "bg-muted"
                }`}>
                  <Fingerprint className={`h-5 w-5 ${useNexus ? "text-teal-600 dark:text-teal-400" : "text-muted-foreground"}`} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {useNexus ? "Using saved profile" : "Use your saved profile"}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {nexusProfile.name || nexusProfile.title || "Your saved career profile"} &middot;{" "}
                    {nexusProfile.raw_resume_text
                      ? `${nexusProfile.raw_resume_text.split(/\s+/).length} words`
                      : "Profile data"}
                  </p>
                </div>
                <div className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                  useNexus
                    ? "border-teal-500 bg-teal-500"
                    : "border-muted-foreground/30"
                }`}>
                  {useNexus && (
                    <svg viewBox="0 0 12 12" className="h-3 w-3 text-white">
                      <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
              </button>
            )}

            {useNexus && nexusProfile && !resumeFile && (
              <p className="text-xs text-muted-foreground">
                Resume text loaded from your saved profile. You can also{" "}
                <button type="button" className="text-teal-600 dark:text-teal-400 underline" onClick={() => setUseNexus(false)}>
                  upload a different resume
                </button>{" "}
                for this application.
              </p>
            )}

            {resumeFile ? (
              <div className="flex items-center gap-3 rounded-xl border p-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{resumeFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(resumeFile.size / 1024).toFixed(0)} KB
                    {resumeText ? ` · ${resumeText.split(/\s+/).length} words extracted` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => {
                    setResumeFile(null);
                    setResumeText("");
                    setResumeUrl("");
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : !useNexus ? (
              <UploadZone
                onUpload={handleResumeUpload}
                accept={{
                  "application/pdf": [".pdf"],
                  "application/msword": [".doc"],
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
                }}
                maxSize={10 * 1024 * 1024}
              />
            ) : null}

            {uploading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Uploading and extracting text…
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Supported formats: PDF, DOC, DOCX (max 10 MB).
            </p>
          </div>
        </div>
      )}

      {step === "review" && (
        <div className="surface-premium rounded-2xl p-6 card-spotlight">
          <h3 className="text-base font-bold">Review Confirmed Facts</h3>
          <p className="mt-1 text-xs text-muted-foreground">Everything looks right? Let’s generate your modules.</p>
          <div className="mt-5 space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border p-3 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Job Title</p>
                <p className="text-sm font-medium">{jobTitle}</p>
              </div>
              <div className="rounded-xl border p-3 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Company</p>
                <p className="text-sm font-medium">{company || "Not specified"}</p>
              </div>
            </div>

            {jdQuality && (
              <div className="rounded-xl border p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-muted-foreground">JD Quality</p>
                  <Badge
                    variant={jdQuality.score >= 70 ? "default" : "secondary"}
                  >
                    {jdQuality.score}/100
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{jdQuality.summary}</p>
                {jdQuality.issues.length > 0 && (
                  <ul className="text-xs text-muted-foreground space-y-0.5">
                    {jdQuality.issues.map((issue, i) => (
                      <li key={i}>⚠ {issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

              <div className="rounded-xl border p-3 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Resume</p>
                <p className="text-sm">
                  {(() => {
                    const wordCount = resumeText.trim()
                      ? resumeText.trim().split(/\s+/).length
                      : 0;
                    if (resumeFile) return `${resumeFile.name} (${wordCount} words)`;
                    if (resumeText.trim()) return `Saved profile used (${wordCount} words)`;
                    return "No resume provided — upload one or set up your profile";
                  })()}
                </p>
              </div>

            <div className="rounded-xl border p-3 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                Keywords ({keywords.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {keywords.map((kw) => (
                  <Badge key={kw} variant="secondary" className="text-xs rounded-lg">
                    {kw}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {step === "generate" && (
        <PipelineAgentView
          progress={progress}
          genMessage={genMessage}
          elapsedMs={elapsedMs}
          completedPhases={completedPhases}
          activePhaseIdx={activePhaseIdx}
          logsByPhase={phaseLogs}
          generating={generating}
          genError={genError}
          onCancel={() => {
            setGenMessage("Cancelling...");
            if (abortRef.current) {
              abortRef.current.abort();
              return;
            }
            if (activeJobId) {
              void cancelGenerationJob(activeJobId).catch((err) => {
                setGenError(err?.message ?? "Failed to cancel generation.");
              });
            }
          }}
          onRetry={() => {
            setStep("review");
            setGenError(null);
            setGenerating(false);
            setProgress(0);
            setGenMessage("");
            setPhaseLogs({});
            setCompletedPhases(new Set());
            setActivePhaseIdx(-1);
            setActiveJobId(null);
            clearGenerationSession();
          }}
          draftAppId={draftAppId}
        />
      )}

      {/* Navigation buttons */}
      {step !== "generate" && (
        <>
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            className="rounded-xl"
            onClick={prevStep}
            disabled={step === "job"}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>

          <Button className="rounded-xl btn-glow" onClick={nextStep} disabled={!canAdvance()}>
            {step === "review" ? (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Application
              </>
            ) : (
              <>
                Next
                <ArrowRight className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </div>
        {step === "job" && !canAdvance() && (jobTitle.trim().length > 0 || jdText.trim().length > 0) && (
          <p className="text-center text-[11px] text-muted-foreground -mt-2">
            {jobTitle.trim().length === 0 ? "Enter a job title to continue" : "Add a more detailed job description to continue"}
          </p>
        )}
        </>
      )}
    </div>
  );
}
