"use client";

import { memo, useEffect, useRef } from "react";
import { CheckCircle2, Loader2, AlertCircle, Circle, type LucideIcon } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

type AgentStatus = "waiting" | "running" | "done" | "failed";

interface AgentTimelineCardProps {
  index: number;
  name: string;
  role: string;
  icon: LucideIcon;
  accentColor: string;
  status: AgentStatus;
  latencyMs?: number;
  logs: string[];
  isLast: boolean;
  errorMessage?: string;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case "done":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500 animate-check-pop" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground/40" />;
  }
}

export const AgentTimelineCard = memo(function AgentTimelineCard({
  name,
  role,
  icon: AgentIcon,
  accentColor,
  status,
  latencyMs,
  logs,
  isLast,
  errorMessage,
}: AgentTimelineCardProps) {
  const logEndRef = useRef<HTMLDivElement>(null);
  const isOpen = status === "running" || status === "failed";

  useEffect(() => {
    if (status === "running" && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs.length, status]);

  return (
    <div className="flex gap-3 relative">
      {/* Timeline connector */}
      <div className="flex flex-col items-center shrink-0 w-6">
        {/* Dot */}
        <div
          className={`relative z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 transition-all duration-500 ${
            status === "running"
              ? "border-primary bg-primary/10 timeline-dot-active"
              : status === "done"
                ? "border-emerald-500 bg-emerald-500/10"
                : status === "failed"
                  ? "border-destructive bg-destructive/10"
                  : "border-border bg-muted/50"
          }`}
        >
          <StatusIcon status={status} />
        </div>
        {/* Connector line */}
        {!isLast && (
          <div
            className={`w-0.5 flex-1 min-h-[8px] transition-colors duration-500 ${
              status === "done" ? "bg-emerald-500/30" : "bg-border"
            }`}
          />
        )}
      </div>

      {/* Card */}
      <details
        className={`flex-1 group outline-none ${status === "waiting" ? "mb-1" : "mb-2"}`}
        open={isOpen || undefined}
      >
        <summary
          className={`list-none cursor-pointer rounded-xl border transition-all duration-500 select-none ${
            status === "waiting" ? "px-3 py-1.5 border-transparent" :
            status === "running"
              ? "p-3 agent-card-active border-border"
              : status === "done"
                ? "p-3 border-border hover:border-emerald-500/30"
                : "p-3 border-destructive/30"
          }`}
        >
          {/* Accent bar for running/failed */}
          {(status === "running" || status === "failed") && (
            <div
              className={`absolute top-0 left-0 right-0 h-0.5 rounded-t-xl ${
                status === "failed" ? "bg-destructive" : `bg-${accentColor}`
              }`}
              style={
                status === "running"
                  ? { background: `var(--agent-accent, hsl(var(--primary)))` }
                  : undefined
              }
            />
          )}

          <div className="flex items-center gap-3">
            {/* Agent avatar */}
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all duration-300 ${
                status === "running"
                  ? "bg-primary/10"
                  : status === "done"
                    ? "bg-emerald-500/10"
                    : status === "failed"
                      ? "bg-destructive/10"
                      : "bg-muted/50"
              }`}
            >
              <AgentIcon
                className={`h-4.5 w-4.5 ${
                  status === "running"
                    ? "text-primary agent-icon-spin"
                    : status === "done"
                      ? "text-emerald-500"
                      : status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground/50"
                }`}
              />
            </div>

            {/* Name + role */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={`text-sm font-semibold ${
                    status === "waiting"
                      ? "text-muted-foreground/60"
                      : "text-foreground"
                  }`}
                >
                  {name}
                </span>
                {status === "done" && latencyMs != null && (
                  <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-2xs font-mono text-emerald-500">
                    {formatLatency(latencyMs)}
                  </span>
                )}
              </div>
              <p className="text-2xs text-muted-foreground truncate">{role}</p>
            </div>

            {/* Expand indicator */}
            <svg
              className="h-4 w-4 text-muted-foreground/40 transition-transform duration-200 group-open:rotate-180"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </summary>

        {/* Expandable log area */}
        <div className="mt-2 ml-12 animate-accordion-down">
          <ScrollArea className="max-h-32 rounded-lg bg-background/50 border border-border/50">
            <div className="p-3 space-y-0.5" role="log" aria-live="polite">
              {logs.length === 0 && status === "running" && (
                <p className="text-2xs text-muted-foreground/50 font-mono italic">
                  Initializing...
                </p>
              )}
              {logs.map((line, i) => (
                <p
                  key={i}
                  className="text-2xs font-mono text-muted-foreground agent-log-line"
                  style={{ animationDelay: `${Math.min(i * 30, 150)}ms` }}
                >
                  <span className="text-muted-foreground/30 mr-2 select-none">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {line}
                </p>
              ))}
              {errorMessage && (
                <p className="text-2xs font-mono text-destructive mt-1">
                  {errorMessage}
                </p>
              )}
              <div ref={logEndRef} />
            </div>
          </ScrollArea>
        </div>
      </details>
    </div>
  );
});
