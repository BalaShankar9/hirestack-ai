"use client";

import { useMemo } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApplicationDoc, ModuleKey } from "@/lib/firestore";

interface TimelineStep {
  label: string;
  done: boolean;
}

function buildSteps(app: ApplicationDoc, evidenceCount: number): TimelineStep[] {
  const m = app.modules ?? {};
  const s = app.scores ?? {};

  const hasFacts = !!app.confirmedFacts;
  const factsLocked = !!app.factsLocked;
  const benchmarkReady = m.benchmark?.state === "ready";
  const gapsReady = m.gaps?.state === "ready";
  const docsReady =
    m.cv?.state === "ready" || m.coverLetter?.state === "ready" || m.personalStatement?.state === "ready";
  const evidenceLinked = evidenceCount > 0 || (s.evidenceStrength ?? 0) > 0;
  const atsChecked = (s.atsReadiness ?? 0) > 0;

  const allModuleKeys: ModuleKey[] = [
    "benchmark", "gaps", "learningPlan", "cv", "coverLetter", "personalStatement", "portfolio",
  ];
  const allReady = allModuleKeys.every((k) => m[k]?.state === "ready");

  return [
    { label: "Inputs captured", done: hasFacts },
    { label: "Facts confirmed", done: factsLocked },
    { label: "Role analysed", done: benchmarkReady },
    { label: "Gaps identified", done: gapsReady },
    { label: "Documents generated", done: docsReady },
    { label: "Evidence linked", done: evidenceLinked },
    { label: "ATS checked", done: atsChecked },
    { label: "Export ready", done: allReady },
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

  return (
    <div className="surface-premium rounded-2xl p-4 card-spotlight">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold">Application Readiness</div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {completedCount}/{steps.length} stages
        </span>
      </div>

      {/* Desktop horizontal stepper */}
      <div className="hidden sm:block">
        <div className="flex items-center gap-0">
          {steps.map((step, idx) => (
            <div key={step.label} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center min-w-0">
                {step.done ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
                ) : (
                  <Circle className="h-5 w-5 text-muted-foreground/30 shrink-0" />
                )}
                <span
                  className={cn(
                    "mt-1.5 text-[10px] leading-tight text-center",
                    step.done ? "text-foreground font-medium" : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div
                  className={cn(
                    "h-0.5 flex-1 mx-1 mt-[-16px]",
                    step.done ? "bg-emerald-500" : "bg-muted",
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Mobile vertical stepper */}
      <div className="sm:hidden space-y-1.5">
        {steps.map((step) => (
          <div key={step.label} className="flex items-center gap-2">
            {step.done ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
            ) : (
              <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
            )}
            <span
              className={cn(
                "text-xs",
                step.done ? "text-foreground font-medium" : "text-muted-foreground",
              )}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
