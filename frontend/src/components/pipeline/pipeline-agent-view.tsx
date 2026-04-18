"use client";

import { useEffect, useMemo, useState } from "react";
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
  Circle,
  Loader2,
  BarChart3,
  BookOpen,
  Mail,
  FolderOpen,
  type LucideIcon,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { AgentMetricsBar } from "./agent-metrics-bar";
import { AgentTimelineCard } from "./agent-timeline-card";

// ── Agent personas with sub-tasks ─────────────────────────────────

interface SubTask {
  key: string;
  label: string;
  pipelineNames?: string[];
}

interface AgentPersona {
  name: string;
  role: string;
  icon: LucideIcon;
  accentColor: string;
  description: string;
  subTasks: SubTask[];
}

const AGENT_PERSONAS: AgentPersona[] = [
  {
    name: "Recon",
    role: "Intel Gatherer",
    icon: Radar,
    accentColor: "cyan-500",
    description: "Researches company, role & market to build intelligence",
    subTasks: [
      { key: "company_research", label: "Company Research" },
      { key: "source_analysis", label: "Source Analysis" },
      { key: "intel_synthesis", label: "Intel Synthesis" },
      { key: "strategy", label: "Strategy Building" },
    ],
  },
  {
    name: "Atlas",
    role: "Resume Analyst",
    icon: ScanSearch,
    accentColor: "blue-500",
    description: "Parses resume and builds detailed candidate benchmark",
    subTasks: [
      { key: "resume_parse", label: "Resume Parsing", pipelineNames: ["resume_parse"] },
      { key: "benchmark", label: "Benchmark Building", pipelineNames: ["benchmark"] },
      { key: "skill_mapping", label: "Skill Mapping" },
    ],
  },
  {
    name: "Cipher",
    role: "Gap Detector",
    icon: SearchCode,
    accentColor: "amber-500",
    description: "Detects skill gaps and ranks improvement priorities",
    subTasks: [
      { key: "gap_detection", label: "Gap Detection", pipelineNames: ["gap_analysis"] },
      { key: "skill_matching", label: "Skill Matching" },
      { key: "priority_ranking", label: "Priority Ranking" },
    ],
  },
  {
    name: "Quill",
    role: "Document Architect",
    icon: PenTool,
    accentColor: "violet-500",
    description: "Generates tailored CV, cover letter & learning plan",
    subTasks: [
      { key: "cv_generation", label: "CV Generation", pipelineNames: ["cv_generation"] },
      { key: "cover_letter", label: "Cover Letter", pipelineNames: ["cover_letter"] },
      { key: "learning_plan", label: "Learning Plan" },
    ],
  },
  {
    name: "Forge",
    role: "Portfolio Builder",
    icon: Hammer,
    accentColor: "teal-500",
    description: "Builds personal statement and professional portfolio",
    subTasks: [
      { key: "personal_statement", label: "Personal Statement", pipelineNames: ["personal_statement"] },
      { key: "portfolio_build", label: "Portfolio", pipelineNames: ["portfolio"] },
    ],
  },
  {
    name: "Sentinel",
    role: "Quality Inspector",
    icon: ShieldCheck,
    accentColor: "emerald-500",
    description: "Validates quality, ATS compliance & fact-checks claims",
    subTasks: [
      { key: "quality_check", label: "Quality Validation" },
      { key: "ats_check", label: "ATS Compliance" },
      { key: "fact_check", label: "Fact Verification" },
    ],
  },
  {
    name: "Nova",
    role: "Final Assembler",
    icon: PackageCheck,
    accentColor: "primary",
    description: "Assembles and packages the final application bundle",
    subTasks: [
      { key: "assembly", label: "Document Assembly" },
      { key: "packaging", label: "Final Packaging" },
    ],
  },
];

// ── Deliverables ────────────────────────────────────────────────

interface Deliverable {
  key: string;
  label: string;
  icon: LucideIcon;
  readyWhenPhase: number;
  pipelineName?: string;
}

const DELIVERABLES: Deliverable[] = [
  { key: "intel", label: "Intel Report", icon: Radar, readyWhenPhase: 0 },
  { key: "benchmark", label: "Benchmark", icon: BarChart3, readyWhenPhase: 1, pipelineName: "benchmark" },
  { key: "gaps", label: "Gap Analysis", icon: SearchCode, readyWhenPhase: 2 },
  { key: "cv", label: "Tailored CV", icon: FileText, readyWhenPhase: 3, pipelineName: "cv_generation" },
  { key: "cover_letter", label: "Cover Letter", icon: Mail, readyWhenPhase: 3, pipelineName: "cover_letter" },
  { key: "learning", label: "Learning Plan", icon: BookOpen, readyWhenPhase: 3 },
  { key: "statement", label: "Statement", icon: PenTool, readyWhenPhase: 4, pipelineName: "personal_statement" },
  { key: "portfolio", label: "Portfolio", icon: FolderOpen, readyWhenPhase: 4, pipelineName: "portfolio" },
  { key: "quality", label: "Quality Score", icon: ShieldCheck, readyWhenPhase: 5 },
  { key: "bundle", label: "Final Pack", icon: PackageCheck, readyWhenPhase: 6 },
];

// ── Progress status labels ────────────────────────────────────────

function getStatusLabel(progress: number, generating: boolean, isComplete: boolean): string {
  if (isComplete) return "Mission Complete";
  if (!generating) return "Mission Control";
  if (progress < 5) return "Initializing Agents";
  if (progress < 28) return "Intelligence Gathering";
  if (progress < 32) return "Profile Analysis";
  if (progress < 48) return "Gap Detection";
  if (progress < 72) return "Document Generation";
  if (progress < 89) return "Portfolio Building";
  if (progress < 96) return "Quality Assurance";
  return "Final Assembly";
}

// ── Sub-task status computation ──────────────────────────────────

type AgentStatus = "waiting" | "running" | "done" | "failed";

function computeSubTaskStatuses(
  parentStatus: AgentStatus,
  subTasks: SubTask[],
  logCount: number,
  pipelineStatuses: Record<string, "running" | "completed">,
): Record<string, AgentStatus> {
  const result: Record<string, AgentStatus> = {};

  if (parentStatus === "done") {
    for (const st of subTasks) result[st.key] = "done";
    return result;
  }

  if (parentStatus === "waiting" || parentStatus === "failed") {
    for (const st of subTasks) result[st.key] = parentStatus;
    return result;
  }

  // parentStatus === "running"
  for (let i = 0; i < subTasks.length; i++) {
    const st = subTasks[i];
    if (st.pipelineNames?.length) {
      const pStatus = st.pipelineNames.reduce<AgentStatus>((acc, pn) => {
        const s = pipelineStatuses[pn];
        if (s === "completed") return "done";
        if (s === "running" && acc !== "done") return "running";
        return acc;
      }, "waiting");
      result[st.key] = pStatus;
    } else {
      // Auto-animated based on log count
      if (logCount >= (i + 1) * 2 + 1) result[st.key] = "done";
      else if (logCount >= i * 2 || i === 0) result[st.key] = "running";
      else result[st.key] = "waiting";
    }
  }

  return result;
}

function getDeliverableStatus(
  d: Deliverable,
  completedPhases: Set<number>,
  activePhaseIdx: number,
  pipelineStatuses: Record<string, "running" | "completed">,
): "done" | "in-progress" | "waiting" {
  const phaseCompleted = completedPhases.has(d.readyWhenPhase);
  const pipelineCompleted = !d.pipelineName || pipelineStatuses[d.pipelineName] === "completed";

  if (phaseCompleted && pipelineCompleted) return "done";
  if (activePhaseIdx === d.readyWhenPhase || (d.pipelineName && pipelineStatuses[d.pipelineName] === "running"))
    return "in-progress";
  return "waiting";
}

// ── Props ────────────────────────────────────────────────────────

interface PipelineAgentViewProps {
  progress: number;
  genMessage: string;
  elapsedMs: number;
  completedPhases: Set<number>;
  activePhaseIdx: number;
  logsByPhase?: Record<number, string[]>;
  pipelineStatuses?: Record<string, "running" | "completed">;
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

const PHASE_LETTERS = ["R", "A", "C", "Q", "F", "S", "N"];

// ── Component ────────────────────────────────────────────────────

export function PipelineAgentView({
  progress,
  genMessage,
  elapsedMs,
  completedPhases,
  activePhaseIdx,
  logsByPhase,
  pipelineStatuses: pipelineStatusesProp,
  generating,
  genError,
  onCancel,
  onRetry,
  draftAppId,
}: PipelineAgentViewProps) {
  const phaseLogs = logsByPhase ?? {};
  const pipelineStatuses = pipelineStatusesProp ?? {};

  // Track per-phase latencies
  const [phaseStartTimes, setPhaseStartTimes] = useState<Record<number, number>>({});
  const [phaseLatencies, setPhaseLatencies] = useState<Record<number, number>>({});

  // Staggered reveal — all 7 agents appear with 120ms stagger
  const [revealedCount, setRevealedCount] = useState(0);
  useEffect(() => {
    if (!generating && revealedCount === 0) return;
    if (revealedCount >= AGENT_PERSONAS.length) return;
    const timer = setTimeout(() => {
      setRevealedCount((prev) => Math.min(prev + 1, AGENT_PERSONAS.length));
    }, 120);
    return () => clearTimeout(timer);
  }, [generating, revealedCount]);

  // Kick off reveal when generation starts
  useEffect(() => {
    if (generating && revealedCount === 0) {
      setRevealedCount(1);
    }
  }, [generating, revealedCount]);

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

  // Derived metrics — count agents that have events but aren't done yet
  const activeAgents = useMemo(() => {
    if (!generating) return 0;
    let count = 0;
    for (let i = 0; i < AGENT_PERSONAS.length; i++) {
      const isDone = completedPhases.has(i);
      const isActive = i === activePhaseIdx && !isDone;
      if (isActive) count++;
    }
    return count;
  }, [generating, completedPhases, activePhaseIdx]);
  const completedCount = completedPhases.size;
  const isComplete = progress >= 100;
  const statusLabel = getStatusLabel(progress, generating, isComplete);

  // Deliverable statuses
  const deliverableStatuses = useMemo(() => {
    const result: Record<string, "done" | "in-progress" | "waiting"> = {};
    for (const d of DELIVERABLES) {
      result[d.key] = getDeliverableStatus(d, completedPhases, activePhaseIdx, pipelineStatuses);
    }
    return result;
  }, [completedPhases, activePhaseIdx, pipelineStatuses]);

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
      <div className="px-6 pb-2">
        <div className="flex items-center justify-between text-2xs text-muted-foreground mb-1.5">
          <span className="font-mono tabular-nums font-medium text-foreground">
            {progress < 100 ? progress.toFixed(1) : "100"}%
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

      {/* Phase indicators */}
      <div className="px-6 pb-3 flex gap-1">
        {AGENT_PERSONAS.map((agent, i) => {
          const isDone = completedPhases.has(i);
          const isActive = i === activePhaseIdx && !isDone;
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
              <div
                className={`h-1 w-full rounded-full transition-all duration-500 ${
                  isDone
                    ? "bg-emerald-500"
                    : isActive
                      ? "bg-blue-500 animate-pulse"
                      : "bg-muted-foreground/15"
                }`}
              />
              <span
                className={`text-[9px] font-mono font-bold leading-none ${
                  isDone
                    ? "text-emerald-500"
                    : isActive
                      ? "text-blue-500"
                      : "text-muted-foreground/30"
                }`}
              >
                {PHASE_LETTERS[i]}
              </span>
            </div>
          );
        })}
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

      {/* Agent Pipeline header */}
      <div className="px-6 pb-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Agent Pipeline
        </h3>
      </div>

      {/* Agent timeline — all agents shown with staggered reveal */}
      <div className="px-6 pb-4">
        <div className="space-y-0">
          {AGENT_PERSONAS.slice(0, revealedCount).map((agent, i) => {
            const isDone = completedPhases.has(i);
            const isActive = i === activePhaseIdx && !isDone;

            let status: AgentStatus = "waiting";
            if (isDone) status = "done";
            else if (isActive) status = "running";

            const subTaskStatuses = computeSubTaskStatuses(
              status,
              agent.subTasks,
              (phaseLogs[i] || []).length,
              pipelineStatuses,
            );

            return (
              <AgentTimelineCard
                key={i}
                index={i}
                name={agent.name}
                role={agent.role}
                icon={agent.icon}
                accentColor={agent.accentColor}
                description={agent.description}
                status={status}
                latencyMs={phaseLatencies[i]}
                logs={phaseLogs[i] || []}
                isLast={i === revealedCount - 1}
                staggerDelay={i * 0.12}
                subTasks={agent.subTasks.map((st) => ({ key: st.key, label: st.label }))}
                subTaskStatuses={subTaskStatuses}
              />
            );
          })}
        </div>
      </div>

      {/* Deliverables grid — always visible */}
      <div className="px-6 pb-4">
        <div className="glass-panel rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2.5">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-semibold text-foreground">Deliverables</span>
            <span className="ml-auto text-[10px] font-mono text-muted-foreground">
              {DELIVERABLES.filter((d) => deliverableStatuses[d.key] === "done").length}/{DELIVERABLES.length}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
            {DELIVERABLES.map((d) => {
              const dStatus = deliverableStatuses[d.key];
              const Icon = d.icon;
              return (
                <div
                  key={d.key}
                  className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 transition-all duration-300 ${
                    dStatus === "done"
                      ? "bg-emerald-500/10"
                      : dStatus === "in-progress"
                        ? "bg-blue-500/10"
                        : "bg-muted/50"
                  }`}
                >
                  {dStatus === "done" ? (
                    <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-500" />
                  ) : dStatus === "in-progress" ? (
                    <Loader2 className="h-3 w-3 shrink-0 text-blue-500 animate-spin" />
                  ) : (
                    <Circle className="h-3 w-3 shrink-0 text-muted-foreground/30" />
                  )}
                  <Icon
                    className={`h-3 w-3 shrink-0 ${
                      dStatus === "done"
                        ? "text-emerald-500"
                        : dStatus === "in-progress"
                          ? "text-blue-500"
                          : "text-muted-foreground/30"
                    }`}
                  />
                  <span
                    className={`text-[10px] leading-tight truncate ${
                      dStatus === "done"
                        ? "text-foreground font-medium"
                        : dStatus === "in-progress"
                          ? "text-foreground"
                          : "text-muted-foreground/50"
                    }`}
                  >
                    {d.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 pb-6 flex flex-col items-center gap-2">
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
