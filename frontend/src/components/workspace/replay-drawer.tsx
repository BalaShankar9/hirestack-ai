"use client";

import { memo, useState, useCallback } from "react";
import { RotateCcw, Loader2, AlertCircle, CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";
import type { ReplayReport } from "@/lib/firestore/models";

interface ReplayDrawerProps {
  jobId: string | null;
  jobStatus: string | null;
  replayReport: ReplayReport | null;
  onRequestReplay: (jobId: string) => Promise<void>;
}

const FAILURE_CLASS_LABELS: Record<string, string> = {
  contract_drift: "Contract mismatch between pipeline stages",
  artifact_gap: "Missing artifacts from completed stages",
  evidence_binding_miss: "Claims not linked to evidence",
  citation_freshness_miss: "Fabricated or unsupported claims detected",
  stage_timeout: "A pipeline stage timed out",
  provider_failure: "AI provider returned an error",
  planner_misclassification: "Pipeline planner chose wrong strategy",
  low_evidence_input: "Not enough evidence to generate reliably",
  validator_escape: "Validator passed despite quality issues",
  unknown: "Unable to classify — manual review needed",
};

export const ReplayDrawer = memo(function ReplayDrawer({
  jobId,
  jobStatus,
  replayReport,
  onRequestReplay,
}: ReplayDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showReplayButton =
    jobId && (jobStatus === "failed" || jobStatus === "error") && !replayReport;

  const handleReplay = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    setError(null);
    try {
      await onRequestReplay(jobId);
    } catch (e: any) {
      setError(e?.message || "Replay failed");
    } finally {
      setLoading(false);
    }
  }, [jobId, onRequestReplay]);

  if (!showReplayButton && !replayReport) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <RotateCcw className="h-3.5 w-3.5" />
          Replay Analysis
        </span>
      </div>

      {showReplayButton && !loading && (
        <button
          onClick={handleReplay}
          className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg border border-dashed border-muted-foreground/30 text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Analyze failure
        </button>
      )}

      {loading && (
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground py-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Running replay analysis…
        </div>
      )}

      {error && (
        <div className="flex items-center gap-1.5 text-[10px] text-destructive">
          <AlertCircle className="h-3 w-3" />
          {error}
        </div>
      )}

      {replayReport && (
        <div className="space-y-2">
          {/* Failure classification */}
          <div className={`rounded-lg px-3 py-2 text-xs ${
            (replayReport.is_failure ?? replayReport.job_status === "failed") ? "bg-destructive/10" : "bg-amber-50"
          }`}>
            <div className="font-semibold">
              {(replayReport.failure_class ?? "unknown").replace(/_/g, " ")}
            </div>
            <div className="text-muted-foreground mt-0.5">
              {FAILURE_CLASS_LABELS[replayReport.failure_class ?? "unknown"] || replayReport.likely_root_cause || "No root cause identified"}
            </div>
          </div>

          {/* Root cause */}
          <div className="text-[11px] text-muted-foreground">
            <span className="font-medium">Root cause:</span>{" "}
            {replayReport.likely_root_cause}
          </div>

          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            Stage details
          </button>

          {expanded && (
            <div className="space-y-1 text-[10px]">
              {replayReport.completed_stages.length > 0 && (
                <div className="flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span>Completed: {replayReport.completed_stages.join(", ")}</span>
                </div>
              )}
              {replayReport.failed_stages.length > 0 && (
                <div className="flex items-center gap-1">
                  <AlertCircle className="h-3 w-3 text-destructive" />
                  <span>Failed: {replayReport.failed_stages.join(", ")}</span>
                </div>
              )}
              {replayReport.timed_out_stages.length > 0 && (
                <div className="flex items-center gap-1 text-amber-500">
                  Timed out: {replayReport.timed_out_stages.join(", ")}
                </div>
              )}
              {replayReport.artifacts_missing.length > 0 && (
                <div className="text-muted-foreground">
                  Missing artifacts: {replayReport.artifacts_missing.join(", ")}
                </div>
              )}
              <div className="text-muted-foreground border-t pt-1 mt-1">
                {replayReport.evidence_count} evidence · {replayReport.citation_count} citations · {replayReport.event_count} events
              </div>
              {replayReport.suggested_regression_target && (
                <div className="italic text-muted-foreground">
                  Suggested test: {replayReport.suggested_regression_target}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
