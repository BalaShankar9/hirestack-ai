"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  CheckCircle2,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import {
  createApplication,
  generateApplicationModules,
  uploadResume,
  computeJDQuality,
  extractKeywords,
  trackEvent,
} from "@/lib/firestore/ops";
import type { ConfirmedFacts, JDQuality, ResumeArtifact } from "@/lib/firestore/models";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { UploadZone } from "@/components/upload-zone";

/* ------------------------------------------------------------------ */
/*  PDF text extraction (client-side via pdf.js)                       */
/* ------------------------------------------------------------------ */

async function extractPdfText(file: File): Promise<string> {
  try {
    const pdfjsLib = await import("pdfjs-dist");
    pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.mjs";

    const buffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
    const pages: string[] = [];

    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const tc = await page.getTextContent();
      pages.push(tc.items.map((item: any) => item.str).join(" "));
    }

    return pages.join("\n\n");
  } catch {
    return "";
  }
}

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

  // Step 4: Generate
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [genError, setGenError] = useState<string | null>(null);

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
        // Extract text
        const text = await extractPdfText(file);
        setResumeText(text);

        // Upload to storage
        const url = await uploadResume(user.uid, file);
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

  /* ---- Generate ---- */
  const handleGenerate = useCallback(async () => {
    if (!user) return;
    setGenerating(true);
    setGenError(null);
    setProgress(0);

    try {
      // Create the application
      const appId = await createApplication(user.uid, jobTitle || "New Application", confirmedFacts);

      await trackEvent(user.uid, "app_created", appId, {
        jobTitle,
        company,
        jdLength: jdText.length,
        hasResume: !!resumeText,
      });

      // Simulate progress while generating
      const interval = setInterval(() => {
        setProgress((p) => Math.min(p + 8, 90));
      }, 500);

      await generateApplicationModules(appId, user.uid, confirmedFacts);

      clearInterval(interval);
      setProgress(100);

      await trackEvent(user.uid, "app_generated", appId);

      // Redirect to workspace
      setTimeout(() => {
        router.push(`/applications/${appId}`);
      }, 600);
    } catch (err: any) {
      setGenError(err?.message ?? "Generation failed");
      setGenerating(false);
    }
  }, [user, jobTitle, company, jdText, resumeText, confirmedFacts, router]);

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
        <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
          <h3 className="text-base font-bold">Paste the Job Description</h3>
          <p className="mt-1 text-xs text-muted-foreground">We’ll extract keywords and build a quality signal.</p>
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Job Title</Label>
                <Input
                  className="rounded-xl h-11"
                  placeholder="Senior Frontend Engineer"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Company (optional)</Label>
                <Input
                  className="rounded-xl h-11"
                  placeholder="TechCorp"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Job Description</Label>
              <Textarea
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
        <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
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
        <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
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
                {resumeFile
                  ? `${resumeFile.name} (${resumeText.split(/\s+/).length} words)`
                  : "No resume uploaded"}
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
        <div className="rounded-2xl border bg-card shadow-soft-sm">
          <div className="flex flex-col items-center justify-center py-16 space-y-4">
            {genError ? (
              <>
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10">
                  <X className="h-7 w-7 text-rose-600" />
                </div>
                <p className="text-sm font-medium text-destructive">
                  {genError}
                </p>
                <Button className="rounded-xl" onClick={() => { setStep("review"); setGenError(null); }}>
                  Try Again
                </Button>
              </>
            ) : (
              <>
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 animate-glow-pulse">
                  <Sparkles className="h-7 w-7 text-primary" />
                </div>
                <p className="text-sm font-semibold">
                  {progress < 100
                    ? "Generating your application modules…"
                    : "Done! Redirecting to workspace…"}
                </p>
                <Progress value={progress} className="w-64" />
                <p className="text-xs text-muted-foreground">
                  Building benchmark, gaps, learning plan, CV, cover letter & scorecard
                </p>
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
