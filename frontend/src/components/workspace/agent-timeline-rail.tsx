"use client";

import { memo } from "react";
import {
  Check,
  Loader2,
  Circle,
  AlertCircle,
  Clock,
  SkipForward,
  RotateCcw,
} from "lucide-react";
import type { AgentStage } from "@/hooks/use-agent-status";
import type { WorkflowState } from "@/lib/firestore/models";

const STAGE_ORDER = [
  "researcher",
  "drafter",
  "critic",
  "optimizer",
  "fact_checker",
  "optimizer_final_analysis",
  "validator",
];

const STAGE_LABELS: Record<string, string> = {
  researcher: "Research & context",
  drafter: "Generate draft",
  critic: "Quality review",
  optimizer: "ATS optimization",
  fact_checker: "Fact verification",
  optimizer_final_analysis: "Final analysis",
  validator: "Validation gate",
};

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <Check className="h-3.5 w-3.5 text-emerald-600" />;
    case "running":
      return <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />;
    case "failed":
      return <AlertCircle className="h-3.5 w-3.5 text-destructive" />;
    case "timed_out":
      return <Clock className="h-3.5 w-3.5 text-amber-500" />;
    case "skipped":
      return <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />;
    default:
      return <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />;
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

interface AgentTimelineRailProps {
  stages: AgentStage[];
  workflowState?: WorkflowState | null;
  isRunning: boolean;
}

export const AgentTimelineRail = memo(function AgentTimelineRail({
  stages,
  workflowState,
  isRunning,
}: AgentTimelineRailProps) {
  // Merge SSE stages with workflow state for a complete picture
  const stageMap = new Map<string, { status: string; latency_ms: number; message: string }>();

  // Populate from workflow state first (authoritative checkpoint data)
  if (workflowState?.stages) {
    for (const [name, checkpoint] of Object.entries(workflowState.stages)) {
      stageMap.set(name, {
        status: checkpoint.status,
        latency_ms: checkpoint.latency_ms ?? 0,
        message: "",
      });
    }
  }

  // Override with live SSE stages (more current during execution)
  for (const stage of stages) {
    stageMap.set(stage.stage, {
      status: stage.status,
      latency_ms: stage.latency_ms,
      message: stage.message,
    });
  }

  // Order stages according to pipeline order, then append any extras
  const orderedStages = STAGE_ORDER
    .filter((name) => stageMap.has(name))
    .map((name) => ({ name, ...stageMap.get(name)! }));

  // Add revision/re-eval stages that aren't in the fixed order
  for (const [name, data] of Array.from(stageMap.entries())) {
    if (!STAGE_ORDER.includes(name)) {
      orderedStages.push({ name, ...data });
    }
  }

  if (orderedStages.length === 0 && !isRunning) return null;

  const totalMs = orderedStages.reduce((sum, s) => sum + (s.latency_ms || 0), 0);
  const failedCount = orderedStages.filter((s) => s.status === "failed").length;
  const revisionStages = orderedStages.filter((s) => s.name.includes("revision"));

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Pipeline Timeline
        </span>
        {totalMs > 0 && (
          <span className="font-mono text-[10px] text-muted-foreground">
            {formatDuration(totalMs)}
          </span>
        )}
      </div>

      <div className="relative pl-4 space-y-0.5">
        {/* Vertical rail line */}
        <div className="absolute left-[6.5px] top-1 bottom-1 w-px bg-border" />

        {orderedStages.map((stage, idx) => {
          const isRevision = stage.name.includes("revision") || stage.name.includes("re_eval");
          return (
            <div
              key={stage.name}
              className={`relative flex items-center gap-2.5 py-1 ${
                isRevision ? "ml-3" : ""
              }`}
            >
              <div className="relative z-10 flex-shrink-0 bg-card">
                <StatusIcon status={stage.status} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  <span
                    className={`text-xs truncate ${
                      stage.status === "running"
                        ? "text-foreground font-medium"
                        : stage.status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground"
                    }`}
                  >
                    {isRevision && <RotateCcw className="inline h-3 w-3 mr-1" />}
                    {STAGE_LABELS[stage.name] || stage.name.replace(/_/g, " ")}
                  </span>
                  {stage.latency_ms > 0 && stage.status === "completed" && (
                    <span className="font-mono text-[10px] text-muted-foreground flex-shrink-0">
                      {formatDuration(stage.latency_ms)}
                    </span>
                  )}
                </div>
                {stage.message && stage.status !== "completed" && (
                  <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                    {stage.message}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary bar */}
      {!isRunning && orderedStages.length > 0 && (
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground pt-1 border-t">
          <span>{orderedStages.filter((s) => s.status === "completed").length} completed</span>
          {failedCount > 0 && (
            <span className="text-destructive">{failedCount} failed</span>
          )}
          {revisionStages.length > 0 && (
            <span>{revisionStages.length} revision(s)</span>
          )}
        </div>
      )}
    </div>
  );
});
