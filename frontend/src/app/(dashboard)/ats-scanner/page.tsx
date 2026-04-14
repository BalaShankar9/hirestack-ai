"use client";

import React, { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useAuth } from "@/components/providers";
import { parseResumeText } from "@/lib/firestore/ops";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  ScanSearch, CheckCircle, XCircle, AlertTriangle, Loader2,
  Upload, FileText, ClipboardPaste, X, Target, ShieldCheck,
  Type, Sparkles, Lightbulb, Copy, ChevronDown, Zap,
  Code, BarChart3, ArrowRight, RefreshCw, Brain, Info,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { AITrace } from "@/components/ui/ai-trace";
import { ScoreExplanation } from "@/components/ui/score-explanation";

/* ── Animation variants ───────────────────────────────────────── */

const fadeUp: any = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.1, duration: 0.5, ease: "easeOut" } }),
};

const staggerContainer: any = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const staggerItem: any = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: "easeOut" } },
};

/* ── Animated progress bar ─────────────────────────────────────── */

function AnimatedBar({ value, label, icon: Icon }: { value: number; label: string; icon?: React.ElementType }) {
  const color = value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-rose-500";
  const textColor = value >= 80 ? "text-emerald-500" : value >= 60 ? "text-amber-500" : "text-rose-500";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium flex items-center gap-1.5">
          {Icon && <Icon className="h-3.5 w-3.5 text-muted-foreground" />} {label}
        </span>
        <span className={cn("text-xs font-bold tabular-nums", textColor)}>{value}/100</span>
      </div>
      <div className="h-2 rounded-full bg-muted/30 overflow-hidden">
        <motion.div
          className={cn("h-full rounded-full", color)}
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
        />
      </div>
    </div>
  );
}

/* ── Score helpers ──────────────────────────────────────────────── */

function scoreColor(v: number) {
  if (v >= 80) return "text-emerald-500";
  if (v >= 60) return "text-amber-500";
  return "text-rose-500";
}
function scoreBg(v: number) {
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-amber-500";
  return "bg-rose-500";
}
function scoreRing(v: number) {
  if (v >= 80) return "stroke-emerald-500";
  if (v >= 60) return "stroke-amber-500";
  return "stroke-rose-500";
}

/* ── Gauge component ──────────────────────────────────────────── */

function Gauge({ value, size = 100, label }: { value: number; size?: number; label: string }) {
  const r = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (value / 100) * circ;
  return (
    <motion.div
      className="flex flex-col items-center gap-1"
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={8} fill="none" className="stroke-muted/20" />
          <motion.circle cx={size / 2} cy={size / 2} r={r} strokeWidth={8} fill="none"
            strokeLinecap="round" strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: "easeOut", delay: 0.3 }}
            className={scoreRing(value)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-xl font-bold tabular-nums", scoreColor(value))}>{value}</span>
        </div>
      </div>
      <span className="text-2xs text-muted-foreground uppercase tracking-wider font-medium">{label}</span>
    </motion.div>
  );
}

/* ── Page ───────────────────────────────────────────────────────── */

export default function ATSScannerPage() {
  const { user, session: authSession } = useAuth();
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [documentContent, setDocumentContent] = useState("");
  const [jdText, setJdText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [scan, setScan] = useState<any>(null);
  const [error, setError] = useState("");

  const handleFileUpload = useCallback(async (file: File) => {
    setUploadedFile(file);
    setParsing(true);
    try {
      const text = await parseResumeText(file);
      if (text && text.trim().length > 10) {
        setDocumentContent(text);
        toast({ title: "Resume parsed", description: `${text.split(/\s+/).length} words extracted` });
      }
    } catch { toast({ title: "Parse failed", description: "Try pasting instead", variant: "error" }); }
    finally { setParsing(false); }
  }, []);

  const runScan = async () => {
    if (!documentContent.trim()) return;
    if (!jdText.trim() || jdText.trim().length < 20) {
      toast({ title: "Job description required", description: "Paste at least a short job description for accurate keyword matching.", variant: "warning" });
      return;
    }
    setLoading(true);
    setError("");
    setScan(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
      const token = authSession?.access_token;
      const res = await fetch(`${API_URL}/api/ats/scan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ document_content: documentContent, jd_text: jdText }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      const raw = await res.json();
      setScan(raw.data ?? raw);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const wordCount = documentContent.trim() ? documentContent.trim().split(/\s+/).length : 0;
  const breakdown = scan?.score_breakdown || {};
  const keywords = scan?.keywords || {};
  const structure = scan?.structure || {};
  const strategy = scan?.strategy || {};

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <motion.div className="flex items-center gap-4" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-glow-sm">
          <ScanSearch className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">ATS Scanner</h1>
          <p className="text-sm text-muted-foreground">3-pass deep analysis — keyword matching, structure parsing, strategic assessment</p>
        </div>
      </motion.div>

      {/* Input Section */}
      <motion.div className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden" variants={fadeUp} initial="hidden" animate="visible" custom={1}>
        <div className="grid lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
          {/* Left: Resume */}
          <div className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold">Your Resume / CV</Label>
              <div className="inline-flex items-center gap-1 rounded-lg border bg-muted/50 p-0.5">
                <button className={cn("flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors", inputMode === "paste" ? "bg-background shadow-sm" : "text-muted-foreground")} onClick={() => setInputMode("paste")}>
                  <ClipboardPaste className="h-3 w-3" /> Paste
                </button>
                <button className={cn("flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors", inputMode === "upload" ? "bg-background shadow-sm" : "text-muted-foreground")} onClick={() => setInputMode("upload")}>
                  <Upload className="h-3 w-3" /> Upload
                </button>
              </div>
            </div>
            {inputMode === "paste" ? (
              <div>
                <Textarea className="h-48 resize-none rounded-xl font-mono text-[13px]" placeholder="Paste your resume/CV text..." value={documentContent} onChange={(e) => setDocumentContent(e.target.value)} maxLength={10000} />
                <div className="flex justify-between text-[11px] text-muted-foreground mt-1">
                  <span>{wordCount > 0 ? `${wordCount} words` : ""}</span>
                  <span>{documentContent.length.toLocaleString()}/10,000</span>
                </div>
              </div>
            ) : (
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFileUpload(f); }}
                className={cn("flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 cursor-pointer transition-colors", uploadedFile ? "border-primary/30 bg-primary/5" : "border-border hover:border-primary/30")}
                onClick={() => fileInputRef.current?.click()}
              >
                <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.doc,.docx,.txt" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }} />
                {parsing ? <Loader2 className="h-6 w-6 text-primary animate-spin" /> : uploadedFile ? (
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-primary" />
                    <div><p className="text-sm font-medium">{uploadedFile.name}</p><p className="text-xs text-muted-foreground">{wordCount} words</p></div>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); setUploadedFile(null); setDocumentContent(""); }}><X className="h-3 w-3" /></Button>
                  </div>
                ) : (
                  <div className="text-center"><Upload className="h-5 w-5 text-muted-foreground mx-auto mb-1" /><p className="text-xs text-muted-foreground">Drop PDF, DOCX, or TXT</p></div>
                )}
              </div>
            )}
          </div>

          {/* Right: JD */}
          <div className="p-5 space-y-3">
            <Label className="text-sm font-semibold">Target Job Description</Label>
            <Textarea className="h-48 resize-none rounded-xl text-[13px]" placeholder="Paste the job description..." value={jdText} onChange={(e) => setJdText(e.target.value)} maxLength={10000} />
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-2xs">Job Title</Label><Input className="rounded-xl h-8 text-sm mt-1" placeholder="e.g. Senior Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} /></div>
              <div><Label className="text-2xs">Company</Label><Input className="rounded-xl h-8 text-sm mt-1" placeholder="e.g. Google" value={company} onChange={(e) => setCompany(e.target.value)} /></div>
            </div>
          </div>
        </div>

        {/* Scan button */}
        <div className="border-t bg-muted/20 px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4 text-2xs text-muted-foreground">
            <span className="flex items-center gap-1"><Target className="h-3 w-3" /> Keywords</span>
            <span className="flex items-center gap-1"><Code className="h-3 w-3" /> Structure</span>
            <span className="flex items-center gap-1"><Brain className="h-3 w-3" /> Strategy</span>
          </div>
          <Button onClick={runScan} disabled={loading || !documentContent.trim()} className="gap-2 rounded-xl px-6">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            {loading ? "Analyzing (3 passes)..." : "Run ATS Scan"}
          </Button>
        </div>
      </motion.div>

      {error && <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="rounded-xl border border-destructive/30 bg-destructive/5 p-4"><p className="text-sm text-destructive">{error}</p></motion.div>}

      {/* ── Results ─────────────────────────────────────────────── */}
      <AnimatePresence>
      {scan && (
        <motion.div className="space-y-4" variants={staggerContainer} initial="hidden" animate="visible" exit={{ opacity: 0, y: 20 }}>
          {/* AI Trace */}
          <AITrace
            variant="banner"
            items={[
              { label: `Analyzed ${wordCount} words`, done: true },
              { label: `${(keywords.present || []).length + (keywords.missing || []).length + (keywords.partial || []).length} keywords evaluated`, done: true },
              { label: `${(keywords.missing || []).length} gaps found`, done: true },
              { label: "3-pass deep analysis complete", done: true },
            ]}
          />

          {/* Score Decomposition */}
          <motion.div variants={staggerItem} className="rounded-2xl border bg-card p-6 shadow-soft-sm">
            <div className="flex flex-col md:flex-row items-center gap-6">
              <Gauge value={scan.ats_score ?? 0} size={130} label="Overall ATS" />
              <div className="h-16 w-px bg-border hidden md:block" />
              <div className="flex items-center gap-6 flex-wrap justify-center">
                <Gauge value={breakdown.keyword_score ?? 0} size={90} label="Keywords" />
                <Gauge value={breakdown.structure_score ?? 0} size={90} label="Structure" />
                <Gauge value={breakdown.strategy_score ?? 0} size={90} label="Strategy" />
              </div>
              <div className="ml-auto text-center md:text-right">
                <motion.div
                  className={cn("text-2xl font-bold uppercase", scan.pass_probability === "high" ? "text-emerald-500" : scan.pass_probability === "medium" ? "text-amber-500" : "text-rose-500")}
                  initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 200, delay: 0.5 }}
                >
                  {scan.pass_probability || "unknown"}
                </motion.div>
                <p className="text-2xs text-muted-foreground">Pass Likelihood</p>
                {strategy.competitive_position && <p className="text-xs text-muted-foreground mt-1">{strategy.competitive_position}</p>}
              </div>
            </div>
            {/* Animated sub-score bars */}
            <div className="grid md:grid-cols-3 gap-4 mt-4 border-t pt-4">
              <AnimatedBar value={breakdown.keyword_score ?? 0} label="Keyword Match" icon={Target} />
              <AnimatedBar value={breakdown.structure_score ?? 0} label="Structure & Format" icon={Code} />
              <AnimatedBar value={breakdown.strategy_score ?? 0} label="Strategic Fit" icon={Brain} />
            </div>
            {/* Score methodology explanation */}
            <div className="mt-4 border-t pt-4">
              <ScoreExplanation
                score={scan.ats_score ?? 0}
                label="ATS Score"
                methodology="Weighted combination: 40% keyword match, 30% document structure & formatting, 30% strategic alignment with the target role."
                factors={[
                  { label: "Keyword Match", impact: (breakdown.keyword_score ?? 0) >= 60 ? "positive" : "negative", detail: `Score: ${breakdown.keyword_score ?? 0}/100 — How many JD keywords appear in your resume` },
                  { label: "Structure & Format", impact: (breakdown.structure_score ?? 0) >= 60 ? "positive" : "negative", detail: `Score: ${breakdown.structure_score ?? 0}/100 — Section completeness, action verbs, quantified results` },
                  { label: "Strategic Fit", impact: (breakdown.strategy_score ?? 0) >= 60 ? "positive" : "negative", detail: `Score: ${breakdown.strategy_score ?? 0}/100 — Role alignment, seniority match, industry relevance` },
                ]}
                improvements={strategy.quick_wins?.slice(0, 3) || []}
              />
            </div>
            {strategy.overall_assessment && (
              <p className="text-sm text-muted-foreground mt-4 border-t pt-4">{strategy.overall_assessment}</p>
            )}
          </motion.div>

          {/* Quick Wins + Deal Breakers */}
          {(strategy.quick_wins?.length > 0 || strategy.deal_breakers?.length > 0) && (
            <motion.div variants={staggerItem} className="grid md:grid-cols-2 gap-4">
              {strategy.quick_wins?.length > 0 && (
                <div className="rounded-2xl border bg-emerald-500/5 border-emerald-500/20 p-4">
                  <h3 className="font-semibold text-sm flex items-center gap-2 text-emerald-600 dark:text-emerald-400 mb-3"><Zap className="h-4 w-4" /> Quick Wins</h3>
                  <ul className="space-y-1.5">
                    {strategy.quick_wins.map((w: string, i: number) => (
                      <li key={i} className="text-xs flex items-start gap-2"><span className="text-emerald-500 font-bold mt-0.5">→</span> {w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {strategy.deal_breakers?.length > 0 && (
                <div className="rounded-2xl border bg-rose-500/5 border-rose-500/20 p-4">
                  <h3 className="font-semibold text-sm flex items-center gap-2 text-rose-600 dark:text-rose-400 mb-3"><AlertTriangle className="h-4 w-4" /> Deal Breakers</h3>
                  <ul className="space-y-1.5">
                    {strategy.deal_breakers.map((d: string, i: number) => (
                      <li key={i} className="text-xs flex items-start gap-2"><span className="text-rose-500 font-bold mt-0.5">✗</span> {d}</li>
                    ))}
                  </ul>
                </div>
              )}
            </motion.div>
          )}

          {/* Keyword Heat Map */}
          <motion.div variants={staggerItem} className="rounded-2xl border bg-card p-5">
            <h3 className="font-semibold text-sm flex items-center gap-2 mb-3"><Target className="h-4 w-4 text-cyan-500" /> Keyword Analysis</h3>
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <p className="text-2xs text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> Present ({(keywords.present || []).length})</p>
                {(keywords.present || []).length > 0 ? (
                  <div className="flex flex-wrap gap-1">{(keywords.present || []).map((k: any, i: number) => <Badge key={i} className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 text-[10px]">{typeof k === "string" ? k : k.keyword || k}</Badge>)}</div>
                ) : (
                  <p className="text-xs text-muted-foreground italic">No matching keywords found — paste a job description for better results</p>
                )}
              </div>
              <div>
                <p className="text-2xs text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1"><XCircle className="h-3 w-3 text-rose-500" /> Missing ({(keywords.missing || []).length})</p>
                {(keywords.missing || []).length > 0 ? (
                  <div className="flex flex-wrap gap-1">{(keywords.missing || []).map((k: any, i: number) => <Badge key={i} className="bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20 text-[10px]">{typeof k === "string" ? k : k.keyword || k}</Badge>)}</div>
                ) : (
                  <p className="text-xs text-emerald-500 font-medium">All keywords accounted for</p>
                )}
              </div>
              <div>
                <p className="text-2xs text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1"><AlertTriangle className="h-3 w-3 text-amber-500" /> Partial ({(keywords.partial || []).length})</p>
                {(keywords.partial || []).length > 0 ? (
                  <div className="flex flex-wrap gap-1">{(keywords.partial || []).map((k: any, i: number) => <Badge key={i} className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 text-[10px]">{typeof k === "string" ? k : k.keyword || k}</Badge>)}</div>
                ) : (
                  <p className="text-xs text-muted-foreground italic">No partial matches</p>
                )}
              </div>
            </div>
            {keywords.critical_missing?.length > 0 && (
              <div className="mt-3 rounded-lg bg-rose-500/5 border border-rose-500/20 p-3">
                <p className="text-xs font-semibold text-rose-500 mb-1">Critical Missing — These will likely cause ATS rejection:</p>
                <div className="flex flex-wrap gap-1">{keywords.critical_missing.map((k: string, i: number) => <Badge key={i} variant="destructive" className="text-[10px]">{k}</Badge>)}</div>
              </div>
            )}
          </motion.div>

          {/* Rewrite Suggestions */}
          {strategy.rewrite_suggestions?.length > 0 && (
            <motion.div variants={staggerItem} className="rounded-2xl border bg-card p-5">
              <h3 className="font-semibold text-sm flex items-center gap-2 mb-4"><Lightbulb className="h-4 w-4 text-primary" /> Rewrite Suggestions</h3>
              <div className="space-y-3">
                {strategy.rewrite_suggestions.map((r: any, i: number) => (
                  <details key={i} className="group rounded-xl border hover:shadow-soft-sm transition-shadow">
                    <summary className="flex items-center gap-3 p-3 cursor-pointer list-none select-none">
                      <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white", r.impact === "high" ? "bg-rose-500" : r.impact === "medium" ? "bg-amber-500" : "bg-blue-500")}>{i + 1}</div>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium">{r.section || "General"}</span>
                        <span className="text-2xs text-muted-foreground ml-2">{r.reason}</span>
                      </div>
                      <Badge variant="outline" className={cn("text-[10px] shrink-0", r.impact === "high" ? "border-rose-500/30 text-rose-500" : "border-amber-500/30 text-amber-500")}>{r.impact}</Badge>
                      <ChevronDown className="h-3 w-3 text-muted-foreground transition-transform group-open:rotate-180" />
                    </summary>
                    <div className="px-3 pb-3 pt-0 border-t space-y-2">
                      {r.current_text && <div className="text-xs"><span className="text-muted-foreground font-medium">Current:</span> <span className="text-muted-foreground line-through">{r.current_text}</span></div>}
                      {r.suggested_text && (
                        <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3 relative">
                          <p className="text-xs text-foreground pr-8">{r.suggested_text}</p>
                          <button className="absolute top-2 right-2 text-muted-foreground hover:text-foreground" onClick={() => { navigator.clipboard.writeText(r.suggested_text); toast({ title: "Copied!" }); }}>
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                      {r.keywords_addressed?.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap">
                          <span className="text-2xs text-muted-foreground">Addresses:</span>
                          {r.keywords_addressed.map((k: string, j: number) => <Badge key={j} className="text-[9px] bg-emerald-500/10 text-emerald-500 border-0">{k}</Badge>)}
                        </div>
                      )}
                    </div>
                  </details>
                ))}
              </div>
            </motion.div>
          )}

          {/* Structure Analysis */}
          {structure.sections_found && (
            <motion.div variants={staggerItem} className="rounded-2xl border bg-card p-5">
              <h3 className="font-semibold text-sm flex items-center gap-2 mb-3"><Code className="h-4 w-4 text-violet-500" /> Structure Analysis</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                {Object.entries(structure.sections_found).map(([section, found]) => (
                  <div key={section} className={cn("flex items-center gap-2 rounded-lg border p-2 text-xs", found ? "bg-emerald-500/5 border-emerald-500/20" : "bg-rose-500/5 border-rose-500/20")}>
                    {found ? <CheckCircle className="h-3 w-3 text-emerald-500 shrink-0" /> : <XCircle className="h-3 w-3 text-rose-500 shrink-0" />}
                    <span className="capitalize">{section.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </div>
              {structure.bullet_quality && (
                <div className="text-xs text-muted-foreground flex items-center gap-4 flex-wrap border-t pt-2">
                  <span>{structure.bullet_quality.total_bullets} bullets</span>
                  <span>{structure.bullet_quality.action_verb_starts} start with action verbs</span>
                  <span>{structure.bullet_quality.quantified_results} have quantified results</span>
                  <Badge variant="outline" className="text-[10px]">Bullet score: {structure.bullet_quality.score}/100</Badge>
                </div>
              )}
              {structure.parsing_issues?.length > 0 && (
                <div className="mt-3 space-y-1">
                  {structure.parsing_issues.map((p: any, i: number) => (
                    <div key={i} className="flex items-start gap-2 text-xs rounded-lg bg-muted/30 p-2">
                      <Badge variant="outline" className={cn("text-[9px] shrink-0", p.severity === "critical" ? "text-rose-500 border-rose-500/30" : p.severity === "major" ? "text-amber-500 border-amber-500/30" : "text-blue-500 border-blue-500/30")}>{p.severity}</Badge>
                      <span>{p.issue}</span>
                      {p.fix && <span className="text-muted-foreground ml-auto shrink-0">Fix: {p.fix}</span>}
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </motion.div>
      )}
      </AnimatePresence>

      {/* Cross-link: Create full application */}
      {scan && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/[0.04] to-transparent p-4"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold">Want a full application package?</p>
                <p className="text-xs text-muted-foreground truncate">Generate a tailored CV, cover letter, gap analysis, and more in one click.</p>
              </div>
            </div>
            <Link href={jdText ? `/new?jdText=${encodeURIComponent(jdText.slice(0, 2000))}` : "/new"}>
              <Button size="sm" className="gap-2 rounded-xl shrink-0">
                Create Application <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </motion.div>
      )}

      {/* Pre-scan guidance */}
      {!scan && !loading && (
        <motion.div className="rounded-2xl border border-dashed bg-card/50 p-8 space-y-6" variants={fadeUp} initial="hidden" animate="visible" custom={2}>
          <div className="flex flex-col md:flex-row items-center gap-6 text-center md:text-left">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 shrink-0">
              <Brain className="h-7 w-7 text-cyan-500" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">What to expect</h3>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-lg">
                Paste your resume and a job description, then hit &ldquo;Run ATS Scan&rdquo;. The analysis runs 3 specialized passes and takes roughly 10–15 seconds.
              </p>
            </div>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            <div className="rounded-xl border bg-muted/20 p-4 space-y-1.5">
              <div className="flex items-center gap-2"><Target className="h-4 w-4 text-cyan-500" /><span className="text-xs font-semibold">Pass 1 — Keywords</span></div>
              <p className="text-xs text-muted-foreground">Extracts every requirement from the JD and checks your resume for exact and semantic matches.</p>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4 space-y-1.5">
              <div className="flex items-center gap-2"><Code className="h-4 w-4 text-violet-500" /><span className="text-xs font-semibold">Pass 2 — Structure</span></div>
              <p className="text-xs text-muted-foreground">Parses sections, bullet quality, and formatting the way ATS systems like Workday or Greenhouse would.</p>
            </div>
            <div className="rounded-xl border bg-muted/20 p-4 space-y-1.5">
              <div className="flex items-center gap-2"><Brain className="h-4 w-4 text-amber-500" /><span className="text-xs font-semibold">Pass 3 — Strategy</span></div>
              <p className="text-xs text-muted-foreground">Evaluates role alignment, identifies deal breakers, and generates copy-paste rewrite suggestions.</p>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
