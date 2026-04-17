"use client";

import { useMemo } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApplicationDoc, ModuleKey } from "@/lib/firestore";

interface TimelineStep {
  label: string;
  detail: string;
  done: boolean;
}

function buildSteps(app: ApplicationDoc, evidenceCount: number): TimelineStep[] {
  const m = app.modules ?? {};
  const s = app.scores ?? {};

  const hasFacts = !!app.confirmedFacts;
  const benchmarkReady = m.benchmark?.state === "ready";
  const gapsReady = m.gaps?.state === "ready";
  const docsReady =
    m.cv?.state === "ready" && m.coverLetter?.state === "ready";
  const polished = evidenceCount > 0 || (s.evidenceStrength ?? 0) > 0;

  const allModuleKeys: ModuleKey[] = [
    "benchmark", "gaps", "learningPlan", "cv", "coverLetter", "personalStatement", "portfolio",
  ];
  const allReady = allModuleKeys.every((k) => m[k]?.state === "ready");
  const atsChecked = (s.atsReadiness ?? 0) > 0;

  return [
    { label: "Profile Ready", detail: "Resume & JD captured", done: hasFacts },
    { label: "Analysis Complete", detail: "Benchmark & gaps scored", done: benchmarkReady && gapsReady },
    { label: "Documents Tailored", detail: "CV & cover letter generated", done: docsReady },
    { label: "Application Polished", detail: "Evidence linked & reviewed", done: polished },
    { label: "Ready to Submit", detail: "ATS scored & all modules done", done: allReady && atsChecked },
  ];
}

export function ReadinessTimeline({
  app,
  evidenceCount,
}: {
  app: ApplicationDoc;
  evidenceCount: number;
}) {
  const steps = useMemo(() => buildSteps(app, evidenceCount), [app, evidenceCount]);
  const completedCount = steps.filter((s) => s.done).length;
  const pct = Math.round((completedCount / steps.length) * 100);

  return (
    <div className="surface-premium rounded-2xl p-4 card-spotlight">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold">Application Readiness</div>
        <span className={cn(
          "text-xs font-semibold tabular-nums",
          pct === 100 ? "text-emerald-500" : "text-muted-foreground",
        )}>
          {pct}%
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-muted overflow-hidden mb-4">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            pct === 100 ? "bg-emerald-500" : pct >= 60 ? "bg-primary" : "bg-amber-500",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={step.label} className="flex items-center gap-2.5">
            {step.done ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
            ) : (
              <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <span
                className={cn(
                  "text-xs leading-tight",
                  step.done ? "text-foreground font-medium" : "text-muted-foreground",
                )}
              >
                {step.label}
              </span>
              <span className="text-[10px] text-muted-foreground/60 ml-1.5">{step.detail}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
