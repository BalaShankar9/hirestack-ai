"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { FileSearch, Loader2, RefreshCw, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface ATSScorePanelProps {
  cvHtml: string;
  jdText: string;
}

function ScoreRing({ value, size = 100, label }: { value: number; size?: number; label: string }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (value / 100) * circ;
  const color = value >= 80 ? "stroke-emerald-500" : value >= 60 ? "stroke-amber-500" : "stroke-rose-500";

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={6} fill="none" className="stroke-muted" />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r} strokeWidth={6} fill="none" strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1, ease: "easeOut" }}
            className={color}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-bold tabular-nums">{value}</span>
        </div>
      </div>
      <span className="text-[10px] text-muted-foreground font-medium">{label}</span>
    </div>
  );
}

function ScoreBar({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-rose-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium">{value}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <motion.div
          className={cn("h-full rounded-full", color)}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

export function ATSScorePanel({ cvHtml, jdText }: ATSScorePanelProps) {
  const { session } = useAuth();
  const [scan, setScan] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stripHtml = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

  const runScan = async () => {
    if (!cvHtml || !jdText) {
      setError("CV and job description are required for ATS scanning.");
      return;
    }
    setScanning(true);
    setError(null);
    try {
      if (session?.access_token) api.setToken(session.access_token);
      const result = await api.request("/ats/scan", {
        method: "POST",
        body: {
          document_content: stripHtml(cvHtml),
          jd_text: jdText,
        },
      });
      setScan(result?.data || result);
    } catch (err: any) {
      setError(err?.message || "ATS scan failed. Please try again.");
    } finally {
      setScanning(false);
    }
  };

  if (!cvHtml) {
    return (
      <div className="rounded-2xl border border-dashed bg-card/50 p-6 sm:p-10 text-center">
        <FileSearch className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
        <h3 className="font-semibold text-sm">Generate your CV first</h3>
        <p className="text-xs text-muted-foreground mt-1">
          The ATS scanner analyzes your generated CV against the job description.
        </p>
      </div>
    );
  }

  if (!scan && !scanning) {
    return (
      <div className="rounded-2xl border bg-card p-6 sm:p-8 text-center space-y-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 mx-auto">
          <FileSearch className="h-7 w-7 text-cyan-500" />
        </div>
        <div>
          <h3 className="font-semibold">Scan your CV for ATS compatibility</h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
            Check keyword coverage, formatting, and structure against the job description.
          </p>
        </div>
        {error && (
          <div className="rounded-xl bg-destructive/10 border border-destructive/20 p-3 max-w-md mx-auto">
            <p className="text-xs text-destructive">{error}</p>
          </div>
        )}
        <Button onClick={runScan} className="rounded-xl gap-2 shadow-glow-sm">
          <FileSearch className="h-4 w-4" />
          Run ATS Scan
        </Button>
      </div>
    );
  }

  if (scanning) {
    return (
      <div className="rounded-2xl border bg-card p-6 sm:p-10 text-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-3" />
        <p className="text-sm font-medium">Analyzing your CV...</p>
        <p className="text-xs text-muted-foreground mt-1">Running keyword match, structure analysis, and strategic assessment</p>
      </div>
    );
  }

  // Results
  const atsScore = scan?.ats_score ?? scan?.overall_score ?? 0;
  const keywordScore = scan?.keyword_score ?? scan?.scores?.keyword ?? 0;
  const formatScore = scan?.format_score ?? scan?.scores?.format ?? 0;
  const structureScore = scan?.structure_score ?? scan?.scores?.structure ?? 0;
  const keywords = scan?.keywords || scan?.matched_keywords || [];
  const missing = scan?.missing_keywords || [];
  const suggestions = scan?.suggestions || scan?.improvements || [];

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      {/* Score overview */}
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
        <div className="flex flex-col md:flex-row items-center gap-6">
          <ScoreRing value={atsScore} size={120} label="Overall ATS Score" />
          <div className="flex-1 w-full space-y-3">
            <ScoreBar label="Keyword Coverage" value={keywordScore} />
            <ScoreBar label="Format & Structure" value={formatScore} />
            <ScoreBar label="Strategic Alignment" value={structureScore} />
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <div className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-semibold",
            atsScore >= 80 ? "bg-emerald-500/10 text-emerald-600" : atsScore >= 60 ? "bg-amber-500/10 text-amber-600" : "bg-rose-500/10 text-rose-600"
          )}>
            {atsScore >= 80 ? <CheckCircle2 className="h-3 w-3" /> : atsScore >= 60 ? <AlertTriangle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {atsScore >= 80 ? "Excellent — likely to pass ATS" : atsScore >= 60 ? "Good — some improvements recommended" : "Needs work — may be filtered out"}
          </div>
          <Button variant="outline" size="sm" className="rounded-xl gap-1.5 text-xs" onClick={runScan} disabled={scanning}>
            <RefreshCw className={cn("h-3 w-3", scanning && "animate-spin")} />
            Re-scan
          </Button>
        </div>
      </div>

      {/* Keywords */}
      {(keywords.length > 0 || missing.length > 0) && (
        <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
          <h3 className="font-semibold text-sm mb-3">Keyword Analysis</h3>
          {keywords.length > 0 && (
            <div className="mb-3">
              <span className="text-[10px] text-muted-foreground block mb-1.5">Matched Keywords</span>
              <div className="flex flex-wrap gap-1">
                {(Array.isArray(keywords) ? keywords : []).map((k: any, i: number) => (
                  <span key={i} className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
                    {typeof k === "string" ? k : k?.keyword || k?.term || String(k)}
                  </span>
                ))}
              </div>
            </div>
          )}
          {missing.length > 0 && (
            <div>
              <span className="text-[10px] text-muted-foreground block mb-1.5">Missing Keywords</span>
              <div className="flex flex-wrap gap-1">
                {(Array.isArray(missing) ? missing : []).map((k: any, i: number) => (
                  <span key={i} className="rounded-full bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-600">
                    {typeof k === "string" ? k : k?.keyword || k?.term || String(k)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
          <h3 className="font-semibold text-sm mb-3">Improvement Suggestions</h3>
          <div className="space-y-2">
            {(Array.isArray(suggestions) ? suggestions : []).map((s: any, i: number) => (
              <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                <span>{typeof s === "string" ? s : s?.suggestion || s?.text || String(s)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
