"use client";

import { memo } from "react";
import { Check, Loader2, Circle, AlertCircle } from "lucide-react";
import type { AgentStage } from "@/hooks/use-agent-status";

const STAGE_LABELS: Record<string, string> = {
  researcher: "Analyzing job requirements",
  drafter: "Creating first draft",
  critic: "Reviewing for quality",
  optimizer: "Optimizing for ATS",
  fact_checker: "Verifying facts",
  validator: "Final validation",
};

function StageIcon({ status }: { status: AgentStage["status"] }) {
  switch (status) {
    case "completed":
      return <Check className="h-4 w-4 text-emerald-600 animate-check-pop" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

interface AgentProgressProps {
  stages: AgentStage[];
  isRunning: boolean;
  pipelineName?: string;
}

export const AgentProgress = memo(function AgentProgress({
  stages,
  isRunning,
  pipelineName,
}: AgentProgressProps) {
  if (stages.length === 0 && !isRunning) return null;

  const completedCount = stages.filter((s) => s.status === "completed").length;
  const totalCount = Math.max(stages.length, 6);
  const progressPct = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="space-y-2">
      {pipelineName && (
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {pipelineName.replace(/_/g, " ")}
        </p>
      )}
      {stages.map((stage) => (
        <div key={stage.stage} className="flex items-center gap-3 text-sm">
          <StageIcon status={stage.status} />
          <span className={stage.status === "running" ? "text-foreground" : "text-muted-foreground"}>
            {STAGE_LABELS[stage.stage] || stage.message || stage.stage}
          </span>
          {stage.status === "completed" && stage.latency_ms > 0 && (
            <span className="font-mono text-xs text-muted-foreground ml-auto">
              {(stage.latency_ms / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      ))}
      {isRunning && (
        <div className="mt-3">
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground font-mono mt-1 text-right">{progressPct}%</p>
        </div>
      )}
    </div>
  );
});
