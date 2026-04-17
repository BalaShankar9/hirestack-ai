"use client";

import { memo } from "react";
import { Timer, Bot, CheckCircle2, Activity } from "lucide-react";

interface AgentMetricsBarProps {
  elapsedMs: number;
  activeAgents: number;
  completedCount: number;
  totalCount: number;
  progress: number;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export const AgentMetricsBar = memo(function AgentMetricsBar({
  elapsedMs,
  activeAgents,
  completedCount,
  totalCount,
  progress,
}: AgentMetricsBarProps) {
  const stats = [
    {
      icon: Timer,
      label: "Elapsed",
      value: formatElapsed(elapsedMs),
      pulse: false,
    },
    {
      icon: Bot,
      label: "Active Agents",
      value: String(activeAgents),
      pulse: activeAgents > 0,
    },
    {
      icon: CheckCircle2,
      label: "Completed",
      value: `${completedCount}/${totalCount}`,
      pulse: false,
    },
    {
      icon: Activity,
      label: "Progress",
      value: `${progress < 100 ? progress.toFixed(1) : "100"}%`,
      pulse: false,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="glass-panel rounded-xl px-3 py-2.5 flex items-center gap-2.5"
        >
          <stat.icon
            className={`h-4 w-4 shrink-0 text-muted-foreground ${
              stat.pulse ? "text-primary animate-pulse" : ""
            }`}
          />
          <div className="min-w-0">
            <p className="text-2xs text-muted-foreground uppercase tracking-wider truncate">
              {stat.label}
            </p>
            <p className="text-sm font-semibold font-mono tabular-nums text-foreground">
              {stat.value}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
});
