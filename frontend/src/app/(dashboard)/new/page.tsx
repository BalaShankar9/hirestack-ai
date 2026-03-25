"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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

/* ------------------------------------------------------------------ */
/*  Page Component                                                      */
/* ------------------------------------------------------------------ */

export default function NewApplicationPage() {
  const router = useRouter();
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;

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

  // Career Nexus profile pre-fill
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
      .catch(() => {})
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
    setActivePhaseIdx(0); // Start with Recon (intel agent) as active

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
      // Agent 0 = Recon (intel gatherer) — runs before SSE events start
      // Agents 1-6 = Atlas, Cipher, Quill, Forge, Sentinel, Nova — mapped from SSE steps 1-6
      const handleProgress = (p: PipelineProgress) => {
        setProgress(p.progress);
        setGenMessage(p.message);

        // Map SSE step (1-based) to phase index (0-based), offset by 1 for Recon
        const phaseIdx = Math.max(0, p.step); // step 1 → phase 1 (Atlas), etc.

        // Mark Recon as done when first SSE arrives (intel gathering is complete)
        setCompletedPhases((prev) => {
          if (!prev.has(0)) {
            const next = new Set(prev);
            next.add(0); // Recon done
            return next;
          }
          return prev;
        });

        setActivePhaseIdx(phaseIdx);

        // Mark phases that are done
        if (p.phase.endsWith("_done") || p.phase === "complete") {
          setCompletedPhases((prev) => {
            const next = new Set(prev);
            next.add(phaseIdx);
            return next;
          });
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
      let message: string;
      if (err?.name === "AbortError") {
        message = "Generation timed out. The AI took too long — please try again.";
      } else if (err?.code === 429 || err?.message?.includes("trial limit")) {
        message = err?.message || "Free trial limit reached. Create a free account to continue.";
      } else {
        message = err?.message ?? "Generation failed — please try again.";
      }
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
            {/* Career Nexus profile pre-fill */}
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
                    {useNexus ? "Using Career Nexus profile" : "Use Career Nexus profile"}
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
                Resume text loaded from your Career Nexus profile. You can also{" "}
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
                  {(() => {
                    const wordCount = resumeText.trim()
                      ? resumeText.trim().split(/\s+/).length
                      : 0;
                    if (resumeFile) return `${resumeFile.name} (${wordCount} words)`;
                    if (resumeText.trim()) return `Career Nexus profile used (${wordCount} words)`;
                    return "No resume — upload one or connect Career Nexus";
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
          generating={generating}
          genError={genError}
          onCancel={() => {
            setGenMessage("Cancelling...");
            abortRef.current?.abort();
          }}
          onRetry={() => { setStep("review"); setGenError(null); }}
          draftAppId={draftAppId}
        />
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
