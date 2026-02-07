"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ModuleStatus } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

function StatusBadge({ status }: { status: ModuleStatus }) {
  if (status.state === "ready") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Ready
      </span>
    );
  }
  if (status.state === "error") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-1 text-[11px] font-medium text-rose-700">
        <AlertTriangle className="h-3.5 w-3.5" />
        Needs attention
      </span>
    );
  }
  if (status.state === "generating" || status.state === "queued") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-[11px] font-medium text-primary">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {status.state === "queued" ? "Queued" : "Generating"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground">
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
  return (
    <div className="rounded-2xl border bg-card p-4 shadow-soft-sm hover:shadow-soft-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 min-w-0">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
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
        <div className="mt-3">
          <Progress value={status.progress} />
          <div className="mt-1 text-[11px] text-muted-foreground">
            Building module… {status.progress}%
          </div>
        </div>
      )}

      {status.state === "error" && status.error ? (
        <div className="mt-3 rounded-xl bg-rose-500/10 p-3 text-xs text-rose-700">
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
        >
          Open
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="rounded-xl"
          onClick={onRegenerate}
          disabled={!onRegenerate}
        >
          Regenerate
        </Button>
      </div>
    </div>
  );
}

