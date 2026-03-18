"use client";

import React, { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/providers";
import { parseResumeText } from "@/lib/firestore/ops";
import type { ATSScan } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  ScanSearch,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Upload,
  FileText,
  ClipboardPaste,
  X,
  Target,
  ShieldCheck,
  Type,
  BarChart3,
  Sparkles,
  ArrowRight,
  Lightbulb,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

/* ── Score color helpers ──────────────────────────────────────────── */

function scoreColor(v: number) {
  if (v >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (v >= 60) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

function scoreBg(v: number) {
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-amber-500";
  return "bg-rose-500";
}

function scoreRingColor(v: number) {
  if (v >= 80) return "stroke-emerald-500";
  if (v >= 60) return "stroke-amber-500";
  return "stroke-rose-500";
}

/* ── Circular score gauge ─────────────────────────────────────────── */

function ScoreGauge({ value, size = 120 }: { value: number; size?: number }) {
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} strokeWidth={10} fill="none" className="stroke-muted" />
        <circle
          cx={size / 2} cy={size / 2} r={radius} strokeWidth={10} fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn("transition-all duration-1000 ease-out", scoreRingColor(value))}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-3xl font-bold tabular-nums", scoreColor(value))}>{value}</span>
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">ATS Score</span>
      </div>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function ATSScannerPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;

  // Input state
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [documentContent, setDocumentContent] = useState("");
  const [jdText, setJdText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Results state
  const [loading, setLoading] = useState(false);
  const [scan, setScan] = useState<ATSScan | null>(null);
  const [error, setError] = useState("");

  /* ── File upload handler ────────────────────────────────────────── */

  const handleFileUpload = useCallback(async (file: File) => {
    setUploadedFile(file);
    setParsing(true);
    try {
      const text = await parseResumeText(file);
      if (text && text.trim().length > 10) {
        setDocumentContent(text);
        toast({ title: "Resume parsed", description: `Extracted ${text.split(/\s+/).length} words from ${file.name}` });
      } else {
        toast({ title: "Parse warning", description: "Could not extract text. Try pasting your resume content instead.", variant: "destructive" });
      }
    } catch (err) {
      toast({ title: "Parse failed", description: "Could not read this file. Try pasting content instead.", variant: "destructive" });
    } finally {
      setParsing(false);
    }
  }, []);

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && (file.type === "application/pdf" || file.name.endsWith(".docx") || file.name.endsWith(".doc") || file.name.endsWith(".txt"))) {
      handleFileUpload(file);
    }
  }, [handleFileUpload]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileUpload(file);
  }, [handleFileUpload]);

  /* ── Run scan ───────────────────────────────────────────────────── */

  const runScan = async () => {
    if (!documentContent.trim()) return;
    setLoading(true);
    setError("");
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${API_URL}/api/ats/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_content: documentContent,
          document_type: "cv",
          job_title: jobTitle,
          company,
          jd_text: jdText,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Scan failed (${res.status})`);
      }
      const result = await res.json();
      setScan(result);
      toast({ title: "Scan complete", description: `ATS score: ${result.ats_score ?? "N/A"}` });
    } catch (e: any) {
      setError(e.message || "Scan failed. Make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const wordCount = documentContent.trim() ? documentContent.trim().split(/\s+/).length : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-soft-sm">
          <ScanSearch className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">ATS Scanner</h1>
          <p className="text-sm text-muted-foreground">
            See your resume through a recruiter's ATS — keyword match, formatting, readability
          </p>
        </div>
      </div>

      {/* ── Input Section ─────────────────────────────────────────── */}
      <div className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden">
        {/* Two-column layout */}
        <div className="grid lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
          {/* Left: Document input */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold">Your Resume / CV</Label>
              <div className="inline-flex items-center gap-1 rounded-lg border bg-muted/50 p-0.5">
                <button
                  type="button"
                  className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors", inputMode === "paste" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
                  onClick={() => setInputMode("paste")}
                >
                  <ClipboardPaste className="h-3 w-3" /> Paste
                </button>
                <button
                  type="button"
                  className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors", inputMode === "upload" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
                  onClick={() => setInputMode("upload")}
                >
                  <Upload className="h-3 w-3" /> Upload
                </button>
              </div>
            </div>

            {inputMode === "paste" ? (
              <div className="space-y-1.5">
                <Textarea
                  className="h-52 resize-none rounded-xl font-mono text-[13px]"
                  placeholder="Paste your resume/CV text here..."
                  value={documentContent}
                  onChange={(e) => setDocumentContent(e.target.value)}
                  maxLength={10000}
                />
                <div className="flex justify-between text-[11px] text-muted-foreground">
                  <span>{wordCount > 0 ? `${wordCount} words` : "No content yet"}</span>
                  <span>{documentContent.length.toLocaleString()}/10,000</span>
                </div>
              </div>
            ) : (
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleFileDrop}
                className={cn(
                  "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 transition-colors cursor-pointer",
                  uploadedFile ? "border-primary/30 bg-primary/5" : "border-border hover:border-primary/30 hover:bg-muted/30"
                )}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={handleFileSelect}
                />
                {parsing ? (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="h-8 w-8 text-primary animate-spin" />
                    <p className="text-sm text-muted-foreground">Extracting text...</p>
                  </div>
                ) : uploadedFile ? (
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                      <FileText className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{uploadedFile.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(uploadedFile.size / 1024).toFixed(0)} KB{wordCount > 0 ? ` · ${wordCount} words extracted` : ""}
                      </p>
                    </div>
                    <Button
                      variant="ghost" size="icon" className="h-8 w-8 ml-2"
                      onClick={(e) => { e.stopPropagation(); setUploadedFile(null); setDocumentContent(""); }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
                      <Upload className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Drop your resume here</p>
                      <p className="text-xs text-muted-foreground">PDF, DOC, DOCX, or TXT (max 10 MB)</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Extracted content preview when using upload */}
            {inputMode === "upload" && documentContent && !parsing && (
              <div className="rounded-xl border bg-muted/30 p-3">
                <p className="text-[11px] font-semibold text-muted-foreground mb-1">Extracted text preview</p>
                <p className="text-xs text-muted-foreground line-clamp-3">{documentContent.slice(0, 300)}...</p>
              </div>
            )}
          </div>

          {/* Right: Job description */}
          <div className="p-5 space-y-4">
            <Label className="text-sm font-semibold">Target Job Description</Label>
            <Textarea
              className="h-52 resize-none rounded-xl text-[13px]"
              placeholder="Paste the job description you're targeting..."
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              maxLength={10000}
            />
            <div className="flex justify-end text-[11px] text-muted-foreground">
              {jdText.length.toLocaleString()}/10,000
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Job Title</Label>
                <Input className="rounded-xl h-9 text-sm" placeholder="e.g. Senior Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Company</Label>
                <Input className="rounded-xl h-9 text-sm" placeholder="e.g. Google" value={company} onChange={(e) => setCompany(e.target.value)} />
              </div>
            </div>
          </div>
        </div>

        {/* Scan button */}
        <div className="border-t bg-muted/20 px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Target className="h-3.5 w-3.5" /> Keyword matching
              </span>
              <span className="flex items-center gap-1.5">
                <Type className="h-3.5 w-3.5" /> Readability analysis
              </span>
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5" /> Format scoring
              </span>
            </div>
            <Button
              onClick={runScan}
              disabled={loading || !documentContent.trim()}
              className="gap-2 rounded-xl px-6"
              size="lg"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
              {loading ? "Scanning..." : "Run ATS Scan"}
            </Button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* ── Results ───────────────────────────────────────────────── */}
      {scan && (
        <div className="space-y-6 animate-fade-in">
          {/* Score overview */}
          <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
            <div className="flex flex-col md:flex-row items-center gap-8">
              {/* Main gauge */}
              <ScoreGauge value={scan.ats_score ?? 0} />

              {/* Sub-scores */}
              <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
                <SubScore icon={<Target className="h-4 w-4" />} label="Keyword Match" value={scan.keyword_match_rate ?? 0} suffix="%" />
                <SubScore icon={<Type className="h-4 w-4" />} label="Readability" value={scan.readability_score ?? 0} />
                <SubScore icon={<ShieldCheck className="h-4 w-4" />} label="Formatting" value={scan.format_score ?? 0} />
                <div className="rounded-xl border p-3 text-center">
                  <div className="flex justify-center mb-1">
                    {scan.pass_prediction === "pass"
                      ? <CheckCircle className="h-5 w-5 text-emerald-500" />
                      : scan.pass_prediction === "fail"
                        ? <XCircle className="h-5 w-5 text-rose-500" />
                        : <AlertTriangle className="h-5 w-5 text-amber-500" />
                    }
                  </div>
                  <div className={cn("text-lg font-bold uppercase", scan.pass_prediction === "pass" ? "text-emerald-600 dark:text-emerald-400" : scan.pass_prediction === "fail" ? "text-rose-600 dark:text-rose-400" : "text-amber-600 dark:text-amber-400")}>
                    {scan.pass_prediction ?? "N/A"}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">Prediction</div>
                </div>
              </div>
            </div>
          </div>

          {/* Keywords grid */}
          <div className="grid md:grid-cols-2 gap-4">
            {/* Matched */}
            <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                <h3 className="text-sm font-semibold">Matched Keywords</h3>
                <Badge variant="secondary" className="ml-auto text-[11px] rounded-lg">{scan.matched_keywords?.length ?? 0}</Badge>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(scan.matched_keywords ?? []).map((k, i) => (
                  <Badge key={i} className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 text-xs rounded-lg border">
                    {k.keyword}
                    {k.frequency > 1 && <span className="ml-1 opacity-60">×{k.frequency}</span>}
                  </Badge>
                ))}
                {(!scan.matched_keywords || scan.matched_keywords.length === 0) && (
                  <p className="text-xs text-muted-foreground">No keywords matched</p>
                )}
              </div>
            </div>

            {/* Missing */}
            <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
              <div className="flex items-center gap-2 mb-3">
                <XCircle className="h-4 w-4 text-rose-500" />
                <h3 className="text-sm font-semibold">Missing Keywords</h3>
                <Badge variant="secondary" className="ml-auto text-[11px] rounded-lg">{scan.missing_keywords?.length ?? 0}</Badge>
              </div>
              <div className="space-y-2">
                {(scan.missing_keywords ?? []).map((k, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <Badge
                      variant="secondary"
                      className={cn("text-[10px] shrink-0 rounded-md border", k.importance === "critical"
                        ? "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800"
                        : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                      )}
                    >
                      {k.importance}
                    </Badge>
                    <span className="font-medium">{k.keyword}</span>
                    {k.suggestion && <span className="text-muted-foreground">— {k.suggestion}</span>}
                  </div>
                ))}
                {(!scan.missing_keywords || scan.missing_keywords.length === 0) && (
                  <p className="text-xs text-muted-foreground">No missing keywords — great coverage!</p>
                )}
              </div>
            </div>
          </div>

          {/* Recommendations */}
          {scan.recommendations && scan.recommendations.length > 0 && (
            <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
              <div className="flex items-center gap-2 mb-4">
                <Lightbulb className="h-4 w-4 text-primary" />
                <h3 className="text-sm font-semibold">Recommendations</h3>
              </div>
              <div className="space-y-2">
                {scan.recommendations.map((r, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-xl border bg-muted/20 p-3">
                    <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white",
                      r.impact === "high" ? "bg-rose-500" : r.impact === "medium" ? "bg-amber-500" : "bg-blue-500"
                    )}>
                      {r.priority}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className={cn("text-[10px] border rounded-md",
                          r.impact === "high" ? "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800" : "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800"
                        )}>
                          {r.impact} impact
                        </Badge>
                      </div>
                      <p className="text-sm mt-1 text-foreground/80">{r.action}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Empty state hint ──────────────────────────────────────── */}
      {!scan && !loading && (
        <div className="rounded-2xl border border-dashed bg-card/50 p-8">
          <div className="flex flex-col md:flex-row items-center gap-6 text-center md:text-left">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-500/10 shrink-0">
              <Sparkles className="h-7 w-7 text-cyan-600 dark:text-cyan-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">How it works</h3>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-lg">
                Paste or upload your resume, add the target job description, and run the scan.
                The AI analyzes keyword coverage, formatting quality, and readability — then gives you
                a pass/fail prediction with actionable recommendations to improve your ATS score.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────── */

function SubScore({ icon, label, value, suffix = "" }: { icon: React.ReactNode; label: string; value: number; suffix?: string }) {
  return (
    <div className="rounded-xl border p-3 text-center">
      <div className="flex justify-center mb-1 text-muted-foreground">{icon}</div>
      <div className={cn("text-lg font-bold tabular-nums", scoreColor(value))}>{value}{suffix}</div>
      <div className="text-[10px] text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}
