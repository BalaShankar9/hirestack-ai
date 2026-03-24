"use client";

import { memo } from "react";
import { Check, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

interface QualityReportProps {
  scores: Record<string, number>;
  factCheck?: { verified: number; enhanced: number; fabricated: number } | null;
  className?: string;
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const color =
    score >= 90 ? "bg-emerald-500" :
    score >= 70 ? "bg-primary" :
    score >= 50 ? "bg-amber-500" :
    "bg-rose-500";

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground w-28 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-600 ease-out", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="font-mono text-sm font-semibold w-12 text-right">{score}%</span>
    </div>
  );
}

export const QualityReport = memo(function QualityReport({
  scores,
  factCheck,
  className,
}: QualityReportProps) {
  const scoreEntries = Object.entries(scores).filter(([, v]) => typeof v === "number");

  if (scoreEntries.length === 0) return null;

  return (
    <div className={cn("space-y-4", className)}>
      <h3 className="text-sm font-semibold">Quality Report</h3>
      <div className="space-y-2.5">
        {scoreEntries.map(([key, value]) => (
          <ScoreBar key={key} label={key.replace(/_/g, " ")} score={value} />
        ))}
      </div>
      {factCheck && (
        <div className="mt-4 space-y-1.5">
          <div className="flex items-center gap-2 text-sm text-emerald-600">
            <Check className="h-3.5 w-3.5" />
            <span>{factCheck.verified} claims verified against your profile</span>
          </div>
          {factCheck.enhanced > 0 && (
            <div className="flex items-center gap-2 text-sm text-primary">
              <Shield className="h-3.5 w-3.5" />
              <span>{factCheck.enhanced} claims strategically enhanced</span>
            </div>
          )}
          {factCheck.fabricated > 0 && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <span className="font-mono font-bold">!</span>
              <span>{factCheck.fabricated} fabricated claims removed</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
