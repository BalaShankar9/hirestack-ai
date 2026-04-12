"use client";

import { useEffect, useState } from "react";
import {
  ScanSearch,
  SearchCode,
  PenTool,
  Hammer,
  ShieldCheck,
  PackageCheck,
  Sparkles,
  X,
  RotateCcw,
  ArrowRight,
  Radar,
  FileText,
  CheckCircle2,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentMetricsBar } from "./agent-metrics-bar";
import { AgentTimelineCard } from "./agent-timeline-card";

// ── Agent personas ───────────────────────────────────────────────

interface AgentPersona {
  name: string;
  role: string;
  icon: LucideIcon;
  accentColor: string;
}

const AGENT_PERSONAS: AgentPersona[] = [
  { name: "Recon", role: "Intel Gatherer", icon: Radar, accentColor: "cyan-500" },
  { name: "Atlas", role: "Resume Analyst", icon: ScanSearch, accentColor: "blue-500" },
  { name: "Cipher", role: "Gap Detector", icon: SearchCode, accentColor: "amber-500" },
  { name: "Quill", role: "Document Architect", icon: PenTool, accentColor: "violet-500" },
  { name: "Forge", role: "Portfolio Builder", icon: Hammer, accentColor: "teal-500" },
  { name: "Sentinel", role: "Quality Inspector", icon: ShieldCheck, accentColor: "emerald-500" },
  { name: "Nova", role: "Final Assembler", icon: PackageCheck, accentColor: "primary" },
];

// ── Progress status labels ────────────────────────────────────────

function getStatusLabel(progress: number, generating: boolean, isComplete: boolean): string {
  if (isComplete) return "Mission Complete";
  if (!generating) return "Mission Control";
  if (progress < 10) return "Initializing Mission";
  if (progress < 30) return "Intelligence Gathering";
  if (progress < 50) return "Analysis Phase";
  if (progress < 75) return "Document Generation";
  if (progress < 90) return "Quality Assurance";
  return "Finalizing";
}

// ── Props ────────────────────────────────────────────────────────

interface PipelineAgentViewProps {
  progress: number;
  genMessage: string;
  elapsedMs: number;
  completedPhases: Set<number>;
  activePhaseIdx: number;
  logsByPhase?: Record<number, string[]>;
  generating: boolean;
  genError: string | null;
  onCancel: () => void;
  onRetry: () => void;
  draftAppId: string | null;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

// ── Component ────────────────────────────────────────────────────

export function PipelineAgentView({
  progress,
  genMessage,
  elapsedMs,
  completedPhases,
  activePhaseIdx,
  logsByPhase,
  generating,
  genError,
  onCancel,
  onRetry,
  draftAppId,
}: PipelineAgentViewProps) {
  const phaseLogs = logsByPhase ?? {};

  // Track per-phase latencies
  const [phaseStartTimes, setPhaseStartTimes] = useState<Record<number, number>>({});
  const [phaseLatencies, setPhaseLatencies] = useState<Record<number, number>>({});

  useEffect(() => {
    if (activePhaseIdx >= 0 && phaseStartTimes[activePhaseIdx] === undefined) {
      setPhaseStartTimes((prev) => ({ ...prev, [activePhaseIdx]: elapsedMs }));
    }
  }, [activePhaseIdx, elapsedMs, phaseStartTimes]);

  useEffect(() => {
    completedPhases.forEach((idx) => {
      if (phaseLatencies[idx] === undefined && phaseStartTimes[idx] !== undefined) {
        setPhaseLatencies((prev) => ({
          ...prev,
          [idx]: elapsedMs - phaseStartTimes[idx],
        }));
      }
    });
  }, [completedPhases, elapsedMs, phaseStartTimes, phaseLatencies]);

  // Derived metrics
  const activeAgents = activePhaseIdx >= 0 && !completedPhases.has(activePhaseIdx) ? 1 : 0;
  const completedCount = completedPhases.size;
  const isComplete = progress >= 100;
  const statusLabel = getStatusLabel(progress, generating, isComplete);

  // ── Error state ──────────────────────────────────────────────

  if (genError) {
    return (
      <div className="surface-premium rounded-2xl">
        <div className="flex flex-col items-center justify-center py-10 px-6 space-y-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10">
            <X className="h-7 w-7 text-rose-600" />
          </div>
          <div className="text-center space-y-1 max-w-md">
            <p className="text-base font-semibold text-destructive">Generation Failed</p>
            <p className="text-sm text-muted-foreground">{genError}</p>
            {(genError.toLowerCase().includes("gemini") ||
              genError.toLowerCase().includes("api_key")) && (
              <p className="mt-2 text-xs text-muted-foreground">
                The AI service is not properly configured. Please try again in a few moments.
              </p>
            )}
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button className="rounded-xl" onClick={onRetry}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Try Again
            </Button>
            {draftAppId && (
              <Button
                variant="outline"
                className="rounded-xl"
                onClick={() => window.location.assign(`/applications/${draftAppId}`)}
              >
                <ArrowRight className="mr-2 h-4 w-4" />
                Open Workspace
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Main pipeline view ───────────────────────────────────────

  return (
    <div className="surface-premium rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="text-center pt-6 pb-3 px-6 space-y-2">
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5">
          <Sparkles
            className={`h-4 w-4 text-primary ${isComplete ? "" : "animate-pulse"}`}
          />
          <span className="text-sm font-semibold text-primary">
            {statusLabel}
          </span>
        </div>
        <p className="text-sm text-muted-foreground min-h-[20px] transition-all duration-300">
          {genMessage || "Initializing agents..."}
        </p>
      </div>

      {/* Overall progress bar */}
      <div className="px-6 pb-3">
        <div className="flex items-center justify-between text-2xs text-muted-foreground mb-1.5">
          <span className="font-mono tabular-nums font-medium text-foreground">
            {progress}%
          </span>
          <span className="flex items-center gap-1">
            {formatElapsed(elapsedMs)}
          </span>
        </div>
        <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-blue-500 via-violet-500 to-emerald-500 transition-all duration-700 ease-out"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
          {!isComplete && progress > 0 && (
            <div
              className="absolute inset-y-0 w-16 rounded-full bg-white/20 animate-shimmer"
              style={{ left: `calc(${progress}% - 32px)` }}
            />
          )}
        </div>
      </div>

      {/* Metrics ribbon */}
      <div className="px-6 pb-3">
        <AgentMetricsBar
          elapsedMs={elapsedMs}
          activeAgents={activeAgents}
          completedCount={completedCount}
          totalCount={AGENT_PERSONAS.length}
          progress={progress}
        />
      </div>

      {/* Agent timeline */}
      <div className="px-6 pb-4">
        <div className="space-y-0">
          {AGENT_PERSONAS.map((agent, i) => {
            const isDone = completedPhases.has(i);
            const isActive = i === activePhaseIdx && !isDone;
            const isFailed = false; // Could be extended per-phase

            let status: "waiting" | "running" | "done" | "failed" = "waiting";
            if (isDone) status = "done";
            else if (isActive) status = "running";
            else if (isFailed) status = "failed";

            return (
              <AgentTimelineCard
                key={i}
                index={i}
                name={agent.name}
                role={agent.role}
                icon={agent.icon}
                accentColor={agent.accentColor}
                status={status}
                latencyMs={phaseLatencies[i]}
                logs={phaseLogs[i] || []}
                isLast={i === AGENT_PERSONAS.length - 1}
              />
            );
          })}
        </div>
      </div>

      {/* Document readiness summary (visible after first docs are done) */}
      {completedCount >= 4 && (
        <div className="px-6 pb-4">
          <div className="glass-panel rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-semibold text-foreground">Documents Preparing</span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { name: "CV", done: completedCount >= 4 },
                { name: "Cover Letter", done: completedCount >= 4 },
                { name: "Personal Statement", done: completedCount >= 5 },
                { name: "Portfolio", done: completedCount >= 5 },
                { name: "Learning Plan", done: completedCount >= 4 },
                { name: "Gap Analysis", done: completedCount >= 3 },
              ].map((doc) => (
                <div key={doc.name} className="flex items-center gap-1.5">
                  <CheckCircle2
                    className={`h-3 w-3 shrink-0 ${
                      doc.done && isComplete
                        ? "text-emerald-500"
                        : doc.done
                          ? "text-primary animate-pulse"
                          : "text-muted-foreground/30"
                    }`}
                  />
                  <span className={`text-[11px] ${doc.done ? "text-foreground" : "text-muted-foreground/50"}`}>
                    {doc.name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="px-6 pb-6 flex flex-col items-center gap-2">
        {/* Contextual hint */}
        <p className="text-xs text-muted-foreground text-center max-w-sm">
          {isComplete
            ? "All agents have completed their work. Your application pack is ready."
            : elapsedMs < 15_000
              ? "Agents are warming up — typical build takes 1-2 minutes."
              : elapsedMs < 60_000
                ? "Making great progress — your application is taking shape."
                : elapsedMs < 300_000
                  ? "Still working — complex applications can take several minutes."
                  : "Still running — keep this tab open while agents finish."}
        </p>

        {isComplete ? (
          draftAppId && (
            <Button
              className="rounded-xl shadow-glow-md"
              onClick={() => window.location.assign(`/applications/${draftAppId}`)}
            >
              <ArrowRight className="mr-2 h-4 w-4" />
              View Application
            </Button>
          )
        ) : (
          <Button
            variant="outline"
            className="rounded-xl"
            disabled={!generating}
            onClick={onCancel}
          >
            <X className="mr-2 h-4 w-4" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}
