"use client";

import { Sparkles, Target, ShieldCheck, ScanEye, Award } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Scorecard } from "@/lib/firestore";

function metricColor(score: number) {
  if (score >= 80) return "text-green-700";
  if (score >= 60) return "text-blue-700";
  if (score >= 40) return "text-amber-700";
  return "text-red-700";
}

function meterColor(score: number) {
  if (score >= 80) return "bg-green-500";
  if (score >= 60) return "bg-blue-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-red-500";
}

function Metric({
  icon,
  label,
  score,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  score: number;
  hint: string;
}) {
  return (
    <div className="rounded-xl border bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-muted-foreground">{icon}</div>
          <div className="text-xs font-medium text-muted-foreground truncate">{label}</div>
        </div>
        <div className={cn("text-sm font-semibold tabular-nums", metricColor(score))}>
          {score}%
        </div>
      </div>
      <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", meterColor(score))} style={{ width: `${score}%` }} />
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground leading-snug">{hint}</div>
    </div>
  );
}

export function ScoreboardHeader({
  title,
  subtitle,
  scorecard,
}: {
  title: string;
  subtitle?: string;
  scorecard: Scorecard;
}) {
  return (
    <div className="sticky top-16 z-20">
      <div className="rounded-2xl border bg-gradient-to-b from-white to-white/60 backdrop-blur supports-[backdrop-filter]:bg-white/50">
        <div className="px-5 pt-5 pb-4">
          <div className="flex flex-col gap-1">
            <div className="text-sm font-semibold text-foreground">{title}</div>
            {subtitle ? (
              <div className="text-xs text-muted-foreground">{subtitle}</div>
            ) : null}
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-5">
            <Metric
              icon={<Target className="h-4 w-4" />}
              label="Match"
              score={scorecard.match}
              hint="Keyword alignment vs the JD."
            />
            <Metric
              icon={<ShieldCheck className="h-4 w-4" />}
              label="ATS readiness"
              score={scorecard.atsReadiness}
              hint="Coverage + structure signal."
            />
            <Metric
              icon={<ScanEye className="h-4 w-4" />}
              label="6‑second scan"
              score={scorecard.recruiterScan}
              hint="Top-third clarity + proof density."
            />
            <Metric
              icon={<Award className="h-4 w-4" />}
              label="Evidence strength"
              score={scorecard.evidenceStrength}
              hint="Proof items supporting claims."
            />
            <div className="rounded-xl border bg-blue-50 p-3">
              <div className="flex items-center gap-2 text-xs font-medium text-blue-900">
                <Sparkles className="h-4 w-4" />
                Top fix (do this next)
              </div>
              <div className="mt-2 text-sm font-semibold text-blue-900 leading-snug">
                {scorecard.topFix}
              </div>
              <div className="mt-2 text-[11px] text-blue-800/80">
                Small moves compound. Ship one fix, snapshot, repeat.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

