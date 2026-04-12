"use client";

import { memo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
      return (
        <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 400, damping: 15 }}>
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
        </motion.div>
      );
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground/30" />;
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
      logEndRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [status]);

  return (
    <motion.div
      className="flex gap-3 relative"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Timeline connector */}
      <div className="flex flex-col items-center shrink-0 w-6">
        <div
          className={`relative z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 transition-all duration-500 ${
            status === "running"
              ? "border-primary bg-primary/10 shadow-[0_0_8px_rgba(var(--primary-rgb,99,102,241),0.3)]"
              : status === "done"
                ? "border-emerald-500 bg-emerald-500/10"
                : status === "failed"
                  ? "border-destructive bg-destructive/10"
                  : "border-border bg-muted/50"
          }`}
        >
          <StatusIcon status={status} />
        </div>
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
        className={`flex-1 group [&:focus]:outline-none [&>summary]:outline-none ${status === "waiting" ? "mb-1" : "mb-2"}`}
        open={isOpen || undefined}
      >
        <summary
          className={`list-none cursor-pointer rounded-xl border transition-all duration-300 select-none outline-none focus:outline-none focus-visible:outline-none ${
            status === "waiting" ? "px-3 py-1.5 border-transparent opacity-50" :
            status === "running"
              ? "p-3 border-primary/20 bg-primary/[0.03] shadow-sm"
              : status === "done"
                ? "p-3 border-border hover:border-emerald-500/30"
                : "p-3 border-destructive/30"
          }`}
        >
          <div className="flex items-center gap-3">
            {/* Agent avatar */}
            <motion.div
              className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors duration-300 ${
                status === "running"
                  ? "bg-primary/10"
                  : status === "done"
                    ? "bg-emerald-500/10"
                    : status === "failed"
                      ? "bg-destructive/10"
                      : "bg-muted/30"
              }`}
              animate={status === "running" ? { scale: [1, 1.05, 1] } : {}}
              transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
            >
              <AgentIcon
                className={`h-[18px] w-[18px] ${
                  status === "running"
                    ? "text-primary"
                    : status === "done"
                      ? "text-emerald-500"
                      : status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground/40"
                }`}
              />
            </motion.div>

            {/* Name + role */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={`text-sm font-semibold transition-colors ${
                    status === "waiting" ? "text-muted-foreground/50" : "text-foreground"
                  }`}
                >
                  {name}
                </span>
                <AnimatePresence>
                  {status === "done" && latencyMs != null && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-600"
                    >
                      {formatLatency(latencyMs)}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
              <p className="text-[10px] text-muted-foreground truncate">{role}</p>
            </div>

            {/* Expand indicator */}
            <svg
              className="h-4 w-4 text-muted-foreground/30 transition-transform duration-200 group-open:rotate-180"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </summary>

        {/* Expandable log area */}
        <div className="mt-2 ml-12">
          <ScrollArea className="max-h-32 rounded-lg bg-zinc-950/80 dark:bg-zinc-950/50 border border-zinc-800/50">
            <div className="p-3 space-y-0.5" role="log" aria-live="polite">
              {logs.length === 0 && status === "running" && (
                <p className="text-[10px] text-zinc-500 font-mono italic">
                  Initializing...
                </p>
              )}
              {logs.map((line, i) => (
                <motion.p
                  key={i}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.15 }}
                  className="text-[10px] font-mono text-zinc-400 leading-relaxed"
                >
                  <span className="text-zinc-600 mr-2 select-none">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {line}
                </motion.p>
              ))}
              {errorMessage && (
                <p className="text-[10px] font-mono text-red-400 mt-1">
                  {errorMessage}
                </p>
              )}
              <div ref={logEndRef} />
            </div>
          </ScrollArea>
        </div>
      </details>
    </motion.div>
  );
});
