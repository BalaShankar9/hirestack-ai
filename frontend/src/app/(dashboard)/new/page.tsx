"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CheckCircle2,
  Circle,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  X,
  Timer,
  RotateCcw,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import {
  createApplication,
  generateApplicationModules,
  patchApplication,
  parseResumeText,
  uploadResume,
  computeJDQuality,
  extractKeywords,
  trackEvent,
} from "@/lib/firestore/ops";
import type { PipelineProgress } from "@/lib/firestore/ops";
import type { ConfirmedFacts, JDQuality, ResumeArtifact } from "@/lib/firestore/models";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { UploadZone } from "@/components/upload-zone";

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

/* ------------------------------------------------------------------ */
/*  Page Component                                                      */
/* ------------------------------------------------------------------ */

export default function NewApplicationPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [step, setStep] = useState<Step>("job");
  const stepIndex = STEPS.findIndex((s) => s.key === step);
  const [draftAppId, setDraftAppId] = useState<string | null>(null);

  // Step 1: Job
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jdText, setJdText] = useState("");
  const [jdQuality, setJdQuality] = useState<JDQuality & { issues: string[]; suggestions: string[] } | null>(null);

  // Step 2: Resume
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [resumeUrl, setResumeUrl] = useState("");
  const [uploading, setUploading] = useState(false);

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

  // Pipeline phases matching the backend SSE events
  const PIPELINE_PHASES = [
    { label: "Parsing resume & building benchmark", icon: "📄" },
    { label: "Analyzing skill gaps", icon: "🔍" },
    { label: "Generating CV, cover letter & learning plan", icon: "✍️" },
    { label: "Building personal statement & portfolio", icon: "📁" },
    { label: "Validating document quality", icon: "✅" },
    { label: "Packaging your application", icon: "📦" },
  ];

  const formatElapsed = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  // Derived
  const keywords = useMemo(() => extractKeywords(jdText), [jdText]);

  /* ---- JD analysis ---- */
  const analyzeJD = useCallback(() => {
    const q = computeJDQuality(jdText);
    setJdQuality(q);
  }, [jdText]);

  /* ---- Resume upload ---- */
  const handleResumeUpload = useCallback(
    async (file: File) => {
      if (!user) return;
      setUploading(true);
      setResumeFile(file);

      try {
        // Server-side text extraction (more reliable than client-side pdf.js across browsers)
        const [text, url] = await Promise.all([
          parseResumeText(file).catch((err) => {
            console.warn("[HireStack] Resume parsing failed:", err);
            return "";
          }),
          uploadResume(user.uid, file),
        ]);

        // Warn if parsing returned empty or very short text (likely parse failure)
        if (!text || text.trim().length < 50) {
          console.warn("[HireStack] Resume text extraction resulted in very short content (possible parse failure)");
          // In a production app with toast system, you might show:
          // toast.warning("Resume extraction incomplete", "The text extraction may have failed. Please review the parsed content.");
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
    if (!user) return;
    // If a previous run is still in-flight, cancel it before starting a new one.
    abortRef.current?.abort();
    setGenerating(true);
    setGenError(null);
    setProgress(0);
    setGenMessage("Initializing AI engine…");
    setElapsedMs(0);
    setCompletedPhases(new Set());
    setActivePhaseIdx(0);

    // Start elapsed timer
    const startTime = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startTime);
    }, 500);

    const controller = new AbortController();
    abortRef.current = controller;

    let appId = draftAppId;
    try {
      if (!appId) {
        appId = await createApplication(
          user.uid,
          jobTitle || "New Application",
          confirmedFacts
        );
        setDraftAppId(appId);

        await trackEvent(user.uid, "app_created", appId, {
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

      // SSE progress callback — drives the entire UI
      const handleProgress = (p: PipelineProgress) => {
        setProgress(p.progress);
        setGenMessage(p.message);

        // Map SSE step (1-based) to phase index (0-based)
        const phaseIdx = Math.max(0, p.step - 1);
        setActivePhaseIdx(phaseIdx);

        // Mark phases that are done (phase ending with "_done")
        if (p.phase.endsWith("_done") || p.phase === "complete") {
          setCompletedPhases((prev) => {
            const next = new Set(prev);
            next.add(phaseIdx);
            return next;
          });
          // Advance active to next phase
          if (p.phase !== "complete") {
            setActivePhaseIdx(phaseIdx + 1);
          }
        }
      };

      await generateApplicationModules(appId, user.uid, confirmedFacts, undefined, handleProgress, {
        signal: controller.signal,
      });

      // Done!
      setProgress(100);
      setGenMessage("Your application is ready! 🎉");
      setCompletedPhases(new Set([0, 1, 2, 3, 4, 5]));
      setActivePhaseIdx(-1);

      await trackEvent(user.uid, "app_generated", appId);
      setDraftAppId(null);

      setTimeout(() => {
        router.push(`/applications/${appId}`);
      }, 1000);
    } catch (err: any) {
      const message = err?.name === "AbortError"
        ? "Generation timed out. The AI took too long — please try again."
        : err?.message ?? "Generation failed — please try again.";
      setGenError(message);
      setGenerating(false);
    } finally {
      // Clear timer in all exit paths (success, error, abort)
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current);
        elapsedRef.current = null;
      }
      abortRef.current = null;
    }
  }, [user, draftAppId, jobTitle, company, jdText, resumeText, confirmedFacts, router]);

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
        <div className="surface-premium rounded-2xl p-6">
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
                <Label htmlFor="company">Company (optional)</Label>
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
              <Label htmlFor="job-description">Job Description</Label>
              <Textarea
                id="job-description"
                rows={12}
                className="rounded-xl"
                placeholder="Paste the full job description here…"
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
              />
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
        <div className="surface-premium rounded-2xl p-6">
          <h3 className="text-base font-bold">Upload Your Resume</h3>
          <p className="mt-1 text-xs text-muted-foreground">Optional but helps generate more accurate analysis.</p>
          <div className="mt-5 space-y-4">
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
            ) : (
              <UploadZone
                onUpload={handleResumeUpload}
                accept={{
                  "application/pdf": [".pdf"],
                  "application/msword": [".doc"],
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
                }}
                maxSize={10 * 1024 * 1024}
              />
            )}

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
        <div className="surface-premium rounded-2xl p-6">
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
                  {/** Avoid showing "1 words" when extraction is empty */}
                  {(() => {
                    const wordCount = resumeText.trim()
                      ? resumeText.trim().split(/\s+/).length
                      : 0;
                    return resumeFile
                      ? `${resumeFile.name} (${wordCount} words)`
                      : "No resume uploaded";
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
        <div className="surface-premium rounded-2xl">
          <div className="flex flex-col items-center justify-center py-10 px-6 space-y-6">
            {genError ? (
              <div className="flex flex-col items-center space-y-4 max-w-md">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10">
                  <X className="h-7 w-7 text-rose-600" />
                </div>
                <div className="text-center space-y-1">
                  <p className="text-base font-semibold text-destructive">Generation Failed</p>
                  <p className="text-sm text-muted-foreground">{genError}</p>
                  {genError.toLowerCase().includes("gemini") || genError.toLowerCase().includes("gemini_api_key") ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      The AI service is not properly configured. Please try again in a few moments, or contact support if the issue persists.
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <Button className="rounded-xl" onClick={() => { setStep("review"); setGenError(null); }}>
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Try Again
                  </Button>
                  {draftAppId && (
                    <Button
                      variant="outline"
                      className="rounded-xl"
                      onClick={() => router.push(`/applications/${draftAppId}`)}
                    >
                      <ArrowRight className="mr-2 h-4 w-4" />
                      Open Workspace
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <>
                {/* Header */}
                <div className="text-center space-y-2">
                  <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5">
                    <Sparkles className="h-4 w-4 text-primary animate-pulse" />
                    <span className="text-sm font-semibold text-primary">
                      {progress >= 100 ? "Complete!" : "Building Your Application"}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{genMessage}</p>
                </div>

                {/* Progress bar with percentage */}
                <div className="w-full max-w-md space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium tabular-nums text-foreground">
                      {progress}%
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <Timer className="h-3 w-3" />
                      {formatElapsed(elapsedMs)}
                    </span>
                  </div>
                  <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-blue-500 via-indigo-500 to-violet-500 transition-all duration-700 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                    {progress < 100 && progress > 0 && (
                      <div
                        className="absolute inset-y-0 w-8 rounded-full bg-white/30 animate-pulse"
                        style={{ left: `calc(${progress}% - 16px)` }}
                      />
                    )}
                  </div>
                </div>

                {/* Phase checklist */}
                <div className="w-full max-w-md rounded-xl border bg-muted/30 p-4 space-y-1">
                  {PIPELINE_PHASES.map((phase, i) => {
                    const isDone = completedPhases.has(i);
                    const isActive = i === activePhaseIdx && !isDone;
                    const isPending = !isDone && !isActive;
                    return (
                      <div
                        key={i}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-300 ${
                          isDone
                            ? "text-foreground"
                            : isActive
                              ? "bg-primary/5 text-foreground font-medium"
                              : "text-muted-foreground/60"
                        }`}
                      >
                        {isDone ? (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                        ) : isActive ? (
                          <Loader2 className="h-4 w-4 shrink-0 text-primary animate-spin" />
                        ) : (
                          <Circle className="h-4 w-4 shrink-0" />
                        )}
                        <span className="flex items-center gap-2">
                          <span>{phase.icon}</span>
                          <span>{phase.label}</span>
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Elapsed time hint */}
                <p className="text-xs text-muted-foreground text-center max-w-sm">
                  {elapsedMs < 15_000
                    ? "Typical: 1–2 min with cloud AI. Local/offline AI can take 5–20 min."
                    : elapsedMs < 60_000
                      ? "Making great progress — your application is taking shape!"
                      : elapsedMs < 300_000
                        ? "Still working — complex applications can take several minutes."
                        : "Still running — keep this tab open while we finish."}
                </p>

                <Button
                  variant="outline"
                  className="rounded-xl"
                  disabled={!generating}
                  onClick={() => {
                    setGenMessage("Cancelling…");
                    abortRef.current?.abort();
                  }}
                >
                  <X className="mr-2 h-4 w-4" />
                  Cancel
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Navigation buttons */}
      {step !== "generate" && (
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

          <Button className="rounded-xl" onClick={nextStep} disabled={!canAdvance()}>
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
      )}
    </div>
  );
}
