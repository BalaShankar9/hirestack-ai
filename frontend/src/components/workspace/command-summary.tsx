"use client";

import {
  Target,
  ShieldCheck,
  ScanEye,
  Award,
  Clock,
  Lock,
  FileCheck,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApplicationDoc } from "@/lib/firestore";

type Scores = NonNullable<ApplicationDoc["scores"]>;

function metricColor(score: number) {
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-blue-600";
  if (score >= 40) return "text-amber-600";
  return "text-rose-600";
}

/** Build a strategic one-liner from score data + gaps. */
function buildStrategicSummary(
  scores: Scores,
  gapCount: number,
  evidenceCount: number,
): string {
  const s = {
    match: scores.match ?? 0,
    ats: scores.atsReadiness ?? 0,
    scan: scores.recruiterScan ?? 0,
    evidence: scores.evidenceStrength ?? 0,
  };

  const overall = Math.round((s.match + s.ats + s.scan + s.evidence) / 4);
  if (overall === 0) return "Generate modules to unlock your application intelligence.";

  const weakest = Object.entries(s).sort(([, a], [, b]) => a - b);
  const [weakKey, weakVal] = weakest[0];

  const nameMap: Record<string, string> = {
    match: "keyword alignment",
    ats: "ATS readiness",
    scan: "recruiter scan clarity",
    evidence: "proof and evidence strength",
  };

  if (overall >= 80) return "Application is strong across all dimensions — focus on polish and export.";
  if (overall >= 60) return `Solid foundation. Biggest opportunity: improve ${nameMap[weakKey]} (${weakVal}%).`;
  if (weakVal < 30) return `Application is underperforming on ${nameMap[weakKey]}. Fix this before applying.`;
  return `${gapCount} gaps identified, ${evidenceCount} evidence items linked. Strengthen ${nameMap[weakKey]} next.`;
}

export function CommandSummary({
  title,
  subtitle,
  scores,
  gapCount,
  evidenceCount,
  modulesCompleted,
  modulesTotal,
  factsLocked,
  updatedAt,
}: {
  title: string;
  subtitle?: string;
  scores?: Scores;
  gapCount: number;
  evidenceCount: number;
  modulesCompleted: number;
  modulesTotal: number;
  factsLocked: boolean;
  updatedAt?: number;
}) {
  const sc = scores ?? {};
  const overall = Math.round(
    ((sc.match ?? 0) + (sc.atsReadiness ?? 0) + (sc.recruiterScan ?? 0) + (sc.evidenceStrength ?? 0)) / 4,
  );
  const summary = buildStrategicSummary(sc, gapCount, evidenceCount);

  return (
    <div className="rounded-2xl border bg-gradient-to-br from-card via-card to-primary/[0.03] shadow-soft-md overflow-hidden relative">
      {/* Decorative accent */}
      <div className="absolute top-0 right-0 w-48 h-48 bg-gradient-to-bl from-primary/5 to-transparent rounded-bl-full pointer-events-none" />

      <div className="relative px-5 pt-5 pb-4">
        {/* Title row */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1 min-w-0">
            <h2 className="text-lg font-bold text-foreground truncate">{title}</h2>
            {subtitle && (
              <div className="text-xs text-muted-foreground">{subtitle}</div>
            )}
            <p className="mt-1 text-sm text-muted-foreground leading-snug max-w-xl">
              {summary}
            </p>
          </div>

          {overall > 0 && (
            <div className="flex items-center gap-2.5 shrink-0 animate-score-reveal">
              <div className={cn("text-3xl font-bold tabular-nums", metricColor(overall))}>
                {overall}%
              </div>
              <div className="text-[10px] font-medium text-muted-foreground leading-tight">
                Overall<br />Readiness
              </div>
            </div>
          )}
        </div>

        {/* Trust signals strip */}
        <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          {updatedAt ? (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Last generated {new Date(updatedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </span>
          ) : null}

          <span className="inline-flex items-center gap-1">
            <Lock className={cn("h-3 w-3", factsLocked ? "text-emerald-500" : "text-muted-foreground/50")} />
            {factsLocked ? "Facts confirmed" : "Facts unconfirmed"}
          </span>

          <span className="inline-flex items-center gap-1">
            <FileCheck className="h-3 w-3" />
            {modulesCompleted}/{modulesTotal} modules built
          </span>

          {evidenceCount > 0 ? (
            <span className="inline-flex items-center gap-1">
              <Award className="h-3 w-3" />
              {evidenceCount} evidence items linked
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-amber-600">
              <Award className="h-3 w-3" />
              No evidence linked yet
            </span>
          )}
        </div>

        {/* Module progress bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-medium text-muted-foreground">Application completeness</span>
            <span className="text-[10px] font-bold tabular-nums text-foreground">{Math.round((modulesCompleted / modulesTotal) * 100)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted/40 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-700 ease-out",
                modulesCompleted === modulesTotal
                  ? "bg-emerald-500"
                  : modulesCompleted >= modulesTotal * 0.5
                    ? "bg-blue-500"
                    : "bg-amber-500"
              )}
              style={{ width: `${(modulesCompleted / modulesTotal) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
