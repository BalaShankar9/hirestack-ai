"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ModuleStatus } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

function StatusBadge({ status }: { status: ModuleStatus }) {
  if (!status) return null;
  if (status.state === "ready") {
    return (
      <span className="chip-premium animate-fade-in gap-1 border-emerald-300/60 bg-emerald-500/10 text-emerald-700 dark:border-emerald-400/30 dark:text-emerald-300">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Ready
      </span>
    );
  }
  if (status.state === "error") {
    return (
      <span className="chip-premium animate-fade-in gap-1 border-rose-300/60 bg-rose-500/10 text-rose-700 dark:border-rose-400/30 dark:text-rose-300">
        <AlertTriangle className="h-3.5 w-3.5" />
        Needs attention
      </span>
    );
  }
  if (status.state === "generating" || status.state === "queued") {
    return (
      <span className="chip-premium gap-1 border-primary/25 bg-primary/10 text-primary">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {status.state === "queued" ? "Queued" : "Generating"}
      </span>
    );
  }
  return (
    <span className="chip-premium gap-1">
      Idle
    </span>
  );
}

export function ModuleCard({
  title,
  description,
  status,
  icon,
  onOpen,
  onRegenerate,
}: {
  title: string;
  description: string;
  status: ModuleStatus;
  icon: React.ReactNode;
  onOpen?: () => void;
  onRegenerate?: () => void;
}) {
  const [regenerating, setRegenerating] = useState(false);
  const isGenerating = status?.state === "generating" || status?.state === "queued";
  const isBusy = regenerating || isGenerating;

  const handleRegenerate = async () => {
    if (!onRegenerate || isBusy) return;
    setRegenerating(true);
    try {
      await onRegenerate();
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="surface-premium group relative overflow-hidden rounded-2xl p-4 transition-all duration-300 hover:border-primary/20 hover:shadow-soft-lg hover:-translate-y-0.5 card-spotlight">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-r from-primary/12 via-violet-500/8 to-transparent" />
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 min-w-0">
          <div className="relative mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary transition-transform duration-200 group-hover:scale-105">
            {icon}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold truncate">{title}</div>
              <StatusBadge status={status} />
            </div>
            <div className="mt-1 text-xs text-muted-foreground leading-snug">
              {description}
            </div>
          </div>
        </div>
      </div>

      {(status.state === "generating" || status.state === "queued") && (
        <div className="mt-3 animate-fade-in">
          <Progress value={status.progress ?? 0} className="h-2" />
          <div className="mt-1 text-[11px] text-muted-foreground">
            Building module… {status.progress ?? 0}%
          </div>
        </div>
      )}

      {status.state === "error" && status.error ? (
        <div className="mt-3 rounded-xl border border-rose-300/50 bg-rose-500/10 p-3 text-xs text-rose-700 animate-fade-in dark:border-rose-400/30 dark:text-rose-300">
          {status.error}
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="default"
          size="sm"
          className="flex-1 rounded-xl"
          onClick={onOpen}
          disabled={!onOpen}
          aria-label={`Open ${title}`}
        >
          Open
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="rounded-xl gap-1.5"
          onClick={handleRegenerate}
          disabled={!onRegenerate || isBusy}
          aria-label={`Regenerate ${title}`}
        >
          {isBusy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {isBusy ? "Working…" : "Regenerate"}
        </Button>
      </div>
    </div>
  );
}
