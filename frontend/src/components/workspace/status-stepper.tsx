"use client";

import { CheckCircle2, Loader2, AlertTriangle, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ModuleKey, ModuleStatus } from "@/lib/firestore";
import { Progress } from "@/components/ui/progress";

const LABELS: Record<ModuleKey, string> = {
  benchmark: "Benchmark",
  gaps: "Gap analysis",
  learningPlan: "Learning plan",
  cv: "Tailored CV",
  coverLetter: "Cover letter",
  scorecard: "Scorecard",
};

function Icon({ status }: { status: ModuleStatus }) {
  if (status.state === "ready") return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  if (status.state === "error") return <AlertTriangle className="h-4 w-4 text-rose-600" />;
  if (status.state === "generating" || status.state === "queued")
    return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
  return <Circle className="h-4 w-4 text-muted-foreground" />;
}

export function StatusStepper({
  modules,
  order = ["benchmark", "gaps", "learningPlan", "cv", "coverLetter", "scorecard"],
}: {
  modules: Record<ModuleKey, ModuleStatus>;
  order?: ModuleKey[];
}) {
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-soft-sm">
      <div className="text-sm font-semibold">Generation progress</div>
      <div className="mt-1 text-xs text-muted-foreground">
        Each module completes independently. You can start using what’s ready.
      </div>

      <div className="mt-4 space-y-3">
        {order.map((key, idx) => {
          const s = modules[key] ?? { state: "idle" };
          return (
            <div key={key} className="flex items-start gap-3">
              <div className="mt-0.5">{<Icon status={s} />}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">{LABELS[key]}</div>
                  <div className="text-[11px] text-muted-foreground tabular-nums">
                    {s.progress ?? 0}%
                  </div>
                </div>
                <div className="mt-2">
                  <Progress value={s.progress ?? 0} />
                </div>
                {s.state === "error" && s.error ? (
                  <div className="mt-2 text-xs text-red-600">{s.error}</div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

