"use client";

import { memo } from "react";
import { Shield, AlertTriangle, TrendingDown, Target, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FinalAnalysisReport, EvidenceSummary, ClaimCitation } from "@/lib/firestore/models";

function riskColor(level: "low" | "medium" | "high" | "critical") {
  switch (level) {
    case "low":
      return "text-emerald-600 bg-emerald-50";
    case "medium":
      return "text-amber-600 bg-amber-50";
    case "high":
      return "text-orange-600 bg-orange-50";
    case "critical":
      return "text-destructive bg-destructive/10";
  }
}

function assessRisk(
  finalAnalysis: FinalAnalysisReport | null,
  evidenceSummary: EvidenceSummary | null,
  citations: ClaimCitation[] | null,
): {
  level: "low" | "medium" | "high" | "critical";
  signals: Array<{ label: string; value: string | number; severity: "ok" | "warn" | "danger" }>;
  confidence: number;
} {
  const signals: Array<{ label: string; value: string | number; severity: "ok" | "warn" | "danger" }> = [];
  let dangerCount = 0;
  let warnCount = 0;

  // Evidence strength
  const evCount = evidenceSummary?.evidence_count ?? 0;
  const evSeverity = evCount >= 5 ? "ok" : evCount >= 2 ? "warn" : "danger";
  signals.push({ label: "Evidence items", value: evCount, severity: evSeverity });
  if (evSeverity === "danger") dangerCount++;
  if (evSeverity === "warn") warnCount++;

  // Contradictions / fabricated
  const fabricated = evidenceSummary?.fabricated_count ?? 0;
  signals.push({
    label: "Fabricated claims",
    value: fabricated,
    severity: fabricated > 0 ? "danger" : "ok",
  });
  if (fabricated > 0) dangerCount++;

  // Unsupported claims
  const unsupported = citations?.filter(
    (c) => c.classification === "unsupported" || c.classification === "embellished"
  ).length ?? 0;
  signals.push({
    label: "Unsupported claims",
    value: unsupported,
    severity: unsupported > 2 ? "danger" : unsupported > 0 ? "warn" : "ok",
  });
  if (unsupported > 2) dangerCount++;
  if (unsupported > 0 && unsupported <= 2) warnCount++;

  // Residual ATS gap
  if (finalAnalysis) {
    const atsScore = finalAnalysis.final_ats_score ?? 0;
    const atsGap = 100 - atsScore;
    signals.push({
      label: "ATS score",
      value: `${atsScore}/100`,
      severity: atsScore >= 75 ? "ok" : atsScore >= 60 ? "warn" : "danger",
    });
    if (atsScore < 60) dangerCount++;
    if (atsScore >= 60 && atsScore < 75) warnCount++;

    // Missing keywords
    const missingKw = finalAnalysis.missing_keywords?.length ?? 0;
    signals.push({
      label: "Missing keywords",
      value: missingKw,
      severity: missingKw > 5 ? "danger" : missingKw > 2 ? "warn" : "ok",
    });
    if (missingKw > 5) dangerCount++;
    if (missingKw > 2 && missingKw <= 5) warnCount++;

    // Residual issues
    signals.push({
      label: "Residual issues",
      value: finalAnalysis.residual_issue_count ?? 0,
      severity: (finalAnalysis.residual_issue_count ?? 0) > 5 ? "danger" : (finalAnalysis.residual_issue_count ?? 0) > 2 ? "warn" : "ok",
    });
  }

  const level = dangerCount >= 2 ? "critical" : dangerCount >= 1 ? "high" : warnCount >= 2 ? "medium" : "low";
  const confidence = finalAnalysis ? 85 : evidenceSummary ? 60 : 30;

  return { level, signals, confidence };
}

interface RiskPanelProps {
  finalAnalysis: FinalAnalysisReport | null;
  evidenceSummary: EvidenceSummary | null;
  citations: ClaimCitation[] | null;
}

export const RiskPanel = memo(function RiskPanel({
  finalAnalysis,
  evidenceSummary,
  citations,
}: RiskPanelProps) {
  if (!finalAnalysis && !evidenceSummary && !citations?.length) return null;

  const { level, signals, confidence } = assessRisk(finalAnalysis, evidenceSummary, citations);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5" />
          Risk Assessment
        </span>
        <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", riskColor(level))}>
          {level.toUpperCase()}
        </span>
      </div>

      <div className="space-y-1">
        {signals.map((signal) => (
          <div key={signal.label} className="flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground">{signal.label}</span>
            <span
              className={cn(
                "font-mono tabular-nums font-medium",
                signal.severity === "ok"
                  ? "text-emerald-600"
                  : signal.severity === "warn"
                  ? "text-amber-600"
                  : "text-destructive"
              )}
            >
              {signal.value}
            </span>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-1 text-[10px] text-muted-foreground pt-1 border-t">
        <Shield className="h-3 w-3" />
        Confidence: {confidence}%
        {!finalAnalysis && <span className="italic ml-1">(no final analysis)</span>}
      </div>
    </div>
  );
});
