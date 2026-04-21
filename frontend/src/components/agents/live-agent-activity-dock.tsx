"use client";

/**
 * LiveAgentActivityDock — global floating drawer that surfaces live
 * agent work no matter which dashboard page the user is on.
 *
 * Subscribes to the user's active (queued/running) generation jobs.
 * When at least one is in flight, renders a collapsed pill at the
 * bottom right; clicking expands a drawer that streams the job event
 * log per agent in real time.
 *
 * Design intent: the user should never wonder "is something happening?"
 * The agentic system is visible everywhere it's working.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Bot,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  X,
  Radar,
  ScanSearch,
  SearchCode,
  PenTool,
  Hammer,
  ShieldCheck,
  PackageCheck,
  Wrench,
  CheckCircle2,
  Database,
  FileCheck,
  GitBranch,
  type LucideIcon,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import {
  useActiveGenerationJobsForUser,
  useGenerationJobEvents,
  type GenerationJobDoc,
  type GenerationJobEventDoc,
} from "@/lib/firestore";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

/** Agent persona registry — keep in sync with pipeline-agent-view.tsx */
const AGENT_REGISTRY: Record<string, { icon: LucideIcon; label: string; accent: string }> = {
  recon: { icon: Radar, label: "Recon", accent: "text-cyan-500" },
  atlas: { icon: ScanSearch, label: "Atlas", accent: "text-blue-500" },
  cipher: { icon: SearchCode, label: "Cipher", accent: "text-amber-500" },
  quill: { icon: PenTool, label: "Quill", accent: "text-violet-500" },
  forge: { icon: Hammer, label: "Forge", accent: "text-teal-500" },
  sentinel: { icon: ShieldCheck, label: "Sentinel", accent: "text-emerald-500" },
  nova: { icon: PackageCheck, label: "Nova", accent: "text-primary" },
};

/** Map an event's stage / pipeline / agent_name field to an agent key. */
function eventToAgent(ev: GenerationJobEventDoc): keyof typeof AGENT_REGISTRY {
  // payload.agent is the most authoritative — set explicitly by the
  // Phase A.3 chain_agent_scope and the Phase B.1 bridge.  Fall back to
  // legacy heuristics for the older progress / detail / agent_status events.
  const payloadAgent = (ev.payload as Record<string, unknown> | undefined)?.agent;
  if (typeof payloadAgent === "string") {
    const direct = payloadAgent.toLowerCase();
    if (direct in AGENT_REGISTRY) return direct as keyof typeof AGENT_REGISTRY;
  }
  const raw = `${ev.agentName ?? ""} ${ev.stage ?? ""} ${ev.payload?.pipeline_name ?? ""}`.toLowerCase();
  if (raw.includes("recon") || raw.includes("intel") || raw.includes("research")) return "recon";
  if (raw.includes("atlas") || raw.includes("resume") || raw.includes("benchmark")) return "atlas";
  if (raw.includes("cipher") || raw.includes("gap")) return "cipher";
  if (raw.includes("quill") || raw.includes("cv_") || raw.includes("cover_letter") || raw.includes("learning")) return "quill";
  if (raw.includes("forge") || raw.includes("portfolio") || raw.includes("personal_statement")) return "forge";
  if (raw.includes("sentinel") || raw.includes("validator") || raw.includes("fact") || raw.includes("critic")) return "sentinel";
  if (raw.includes("nova") || raw.includes("assemble") || raw.includes("package")) return "nova";
  return "recon";
}

/** Human-readable status string for a job. */
function statusLabel(job: GenerationJobDoc): string {
  if (job.status === "queued") return "Queued";
  if (job.status === "running") {
    const agent = job.currentAgent ? AGENT_REGISTRY[job.currentAgent.toLowerCase()]?.label ?? job.currentAgent : null;
    return agent ? `${agent} working…` : "Working…";
  }
  return job.status ?? "";
}

/** Per-agent latest log line, used in the collapsed view. */
function deriveAgentSummaries(events: GenerationJobEventDoc[]) {
  const summary: Record<string, { latest: string; agentKey: keyof typeof AGENT_REGISTRY; ts: number }> = {};
  for (const ev of events) {
    const agentKey = eventToAgent(ev);
    const line = ev.message?.trim() || "";
    if (!line) continue;
    const ts = typeof ev.createdAt === "number" ? ev.createdAt : 0;
    const prev = summary[agentKey];
    if (!prev || ts >= prev.ts) {
      summary[agentKey] = { latest: line, agentKey, ts };
    }
  }
  return summary;
}

/** Map an enriched event_name to a small icon for in-feed glanceability. */
function eventTypeIcon(name?: string | null): LucideIcon | null {
  switch (name) {
    case "tool_call":
      return Wrench;
    case "tool_result":
      return CheckCircle2;
    case "cache_hit":
      return Database;
    case "evidence_added":
      return FileCheck;
    case "policy_decision":
      return GitBranch;
    default:
      return null;
  }
}

function eventTypeTint(name?: string | null): string {
  switch (name) {
    case "tool_call":
      return "text-amber-500";
    case "tool_result":
      return "text-emerald-500";
    case "cache_hit":
      return "text-cyan-500";
    case "evidence_added":
      return "text-violet-500";
    case "policy_decision":
      return "text-blue-500";
    default:
      return "";
  }
}

/** Pull a short trailing detail from enriched event payloads. */
function enrichedEventDetail(ev: GenerationJobEventDoc): string {
  const p = (ev.payload ?? {}) as Record<string, unknown>;
  switch (ev.eventName) {
    case "tool_call":
      return p.tool ? `· ${String(p.tool)}` : "";
    case "tool_result": {
      const parts: string[] = [];
      if (p.tool) parts.push(String(p.tool));
      if (typeof p.latency_ms === "number") parts.push(`${p.latency_ms}ms`);
      if (p.cache_hit === true) parts.push("cached");
      return parts.length ? `· ${parts.join(" · ")}` : "";
    }
    case "cache_hit":
      return p.cache ? `· ${String(p.cache)}` : "";
    case "evidence_added": {
      const parts: string[] = [];
      if (p.tier) parts.push(String(p.tier));
      if (p.cross_confirmed === true) parts.push("cross-confirmed");
      return parts.length ? `· ${parts.join(" · ")}` : "";
    }
    case "policy_decision":
      return p.decision ? `· ${String(p.decision)}` : "";
    default:
      return "";
  }
}

/** ── Single-job event feed (expanded drawer body) ───────────────── */
function JobLiveFeed({ job }: { job: GenerationJobDoc }) {
  const { data: events } = useGenerationJobEvents(job.id, 200, { live: true });

  const grouped = useMemo(() => {
    const byAgent = new Map<keyof typeof AGENT_REGISTRY, GenerationJobEventDoc[]>();
    for (const ev of events) {
      const key = eventToAgent(ev);
      const arr = byAgent.get(key) ?? [];
      arr.push(ev);
      byAgent.set(key, arr);
    }
    return byAgent;
  }, [events]);

  const orderedKeys: (keyof typeof AGENT_REGISTRY)[] = ["recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova"];
  const visibleAgents = orderedKeys.filter((k) => (grouped.get(k)?.length ?? 0) > 0);

  return (
    <div className="space-y-3">
      {/* Job-level meta */}
      <div className="rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{statusLabel(job)}</span>
          <span className="text-muted-foreground">
            {job.completedSteps}/{job.totalSteps || "?"} steps · {job.progress ?? 0}%
          </span>
        </div>
        {job.message ? (
          <div className="mt-1 truncate text-muted-foreground">{job.message}</div>
        ) : null}
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(2, job.progress ?? 0))}%` }}
          />
        </div>
      </div>

      {visibleAgents.length === 0 ? (
        <div className="flex items-center gap-2 px-3 py-6 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Waiting for first agent event…
        </div>
      ) : null}

      {/* Per-agent feeds */}
      {visibleAgents.map((agentKey) => {
        const meta = AGENT_REGISTRY[agentKey];
        const Icon = meta.icon;
        const lines = grouped.get(agentKey) ?? [];
        return (
          <div key={agentKey} className="rounded-lg border border-border/40 bg-card">
            <div className="flex items-center gap-2 border-b border-border/30 px-3 py-1.5">
              <Icon className={cn("h-3.5 w-3.5", meta.accent)} />
              <span className="text-xs font-semibold">{meta.label}</span>
              <span className="ml-auto text-[10px] text-muted-foreground">
                {lines.length} event{lines.length === 1 ? "" : "s"}
              </span>
            </div>
            <ScrollArea className="max-h-32">
              <div className="space-y-0.5 px-3 py-2 font-mono text-[11px] leading-snug">
                {lines.slice(-12).map((ev) => {
                  const EventIcon = eventTypeIcon(ev.eventName);
                  const eventTint = eventTypeTint(ev.eventName);
                  const detail = enrichedEventDetail(ev);
                  return (
                    <div key={ev.id} className="flex items-start gap-1.5 text-muted-foreground">
                      <span className="text-muted-foreground/60 shrink-0">
                        {typeof ev.createdAt === "number"
                          ? new Date(ev.createdAt).toLocaleTimeString()
                          : ""}
                      </span>
                      {EventIcon ? (
                        <EventIcon className={cn("h-3 w-3 mt-[2px] shrink-0", eventTint)} />
                      ) : null}
                      <span
                        className={cn(
                          "min-w-0 break-words",
                          ev.status === "completed" && "text-emerald-500",
                          ev.status === "failed" && "text-destructive",
                          ev.status === "running" && "text-primary",
                          eventTint && !ev.status && eventTint,
                        )}
                      >
                        {ev.message || ev.eventName}
                        {detail ? (
                          <span className="ml-1 text-muted-foreground/70">{detail}</span>
                        ) : null}
                      </span>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        );
      })}
    </div>
  );
}

/** ── Main dock component ─────────────────────────────────────────── */
export function LiveAgentActivityDock() {
  const { user } = useAuth();
  const userId = user?.uid || (user as { id?: string } | null)?.id || null;

  const { data: activeJobs } = useActiveGenerationJobsForUser(userId);
  const [expanded, setExpanded] = useState(false);
  const [dismissedJobIds, setDismissedJobIds] = useState<Set<string>>(new Set());

  const visibleJobs = useMemo(
    () => activeJobs.filter((j) => !dismissedJobIds.has(j.id)),
    [activeJobs, dismissedJobIds],
  );

  // When a new job appears, show but don't auto-expand. Don't surprise the user.
  useEffect(() => {
    if (visibleJobs.length === 0) {
      setExpanded(false);
    }
  }, [visibleJobs.length]);

  const headJob = visibleJobs[0] ?? null;
  const { data: headEvents } = useGenerationJobEvents(headJob?.id ?? null, 50, { live: true });
  const summary = useMemo(() => deriveAgentSummaries(headEvents), [headEvents]);
  const summaryAgents = Object.values(summary).slice(-3);

  if (!userId || visibleJobs.length === 0 || !headJob) return null;

  const hasMultiple = visibleJobs.length > 1;

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2"
      aria-label="Live agent activity"
    >
      <AnimatePresence>
        {expanded ? (
          <motion.div
            key="expanded"
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.96 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="pointer-events-auto w-[380px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-border bg-background shadow-2xl"
          >
            <div className="flex items-center gap-2 border-b border-border/50 px-4 py-3">
              <Activity className="h-4 w-4 animate-pulse text-primary" />
              <span className="text-sm font-semibold">Agents Working</span>
              <span className="text-xs text-muted-foreground">
                · {visibleJobs.length} job{visibleJobs.length === 1 ? "" : "s"}
              </span>
              <div className="ml-auto flex items-center gap-1">
                <Link
                  href={`/applications/${headJob.applicationId}`}
                  className="text-xs text-muted-foreground hover:text-foreground"
                  title="Open application"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Collapse"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
              </div>
            </div>

            <ScrollArea className="max-h-[60vh]">
              <div className="space-y-4 p-3">
                <JobLiveFeed job={headJob} />
                {hasMultiple ? (
                  <div className="space-y-2">
                    <div className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Other active jobs
                    </div>
                    {visibleJobs.slice(1).map((j) => (
                      <Link
                        key={j.id}
                        href={`/applications/${j.applicationId}`}
                        className="flex items-center gap-2 rounded-lg border border-border/40 px-3 py-2 text-xs hover:border-border hover:bg-muted/40"
                      >
                        <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="flex-1 truncate">{statusLabel(j)}</span>
                        <span className="text-muted-foreground">{j.progress ?? 0}%</span>
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            </ScrollArea>

            <div className="flex items-center justify-between gap-2 border-t border-border/50 bg-muted/30 px-3 py-2 text-xs">
              <span className="text-muted-foreground">
                Streaming live · auto-closes when done
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  setDismissedJobIds(new Set(visibleJobs.map((j) => j.id)));
                  setExpanded(false);
                }}
              >
                <X className="mr-1 h-3 w-3" /> Hide
              </Button>
            </div>
          </motion.div>
        ) : (
          <motion.button
            key="collapsed"
            type="button"
            initial={{ opacity: 0, y: 16, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.9 }}
            transition={{ duration: 0.2 }}
            onClick={() => setExpanded(true)}
            className="pointer-events-auto group flex max-w-[min(420px,calc(100vw-2rem))] items-center gap-3 rounded-full border border-border bg-background py-2 pl-3 pr-4 shadow-xl ring-1 ring-primary/20 hover:border-primary/40 hover:ring-primary/40"
            aria-label="Expand live agent activity"
          >
            <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <Activity className="h-3.5 w-3.5 text-primary" />
              <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
              </span>
            </div>

            <div className="flex min-w-0 flex-1 flex-col items-start text-left">
              <span className="text-xs font-semibold text-foreground">
                {statusLabel(headJob)}
              </span>
              <span className="truncate text-[11px] text-muted-foreground">
                {summaryAgents.length > 0
                  ? summaryAgents[summaryAgents.length - 1].latest
                  : `${headJob.completedSteps}/${headJob.totalSteps || "?"} steps`}
              </span>
            </div>

            <ChevronUp className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground" />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
