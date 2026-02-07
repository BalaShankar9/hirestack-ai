"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Circle, Filter, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskDoc } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export function TaskQueue({
  tasks,
  onToggle,
  onOpenWorkspace,
  compact = false,
}: {
  tasks: TaskDoc[];
  onToggle: (task: TaskDoc) => void;
  onOpenWorkspace?: (appId: string) => void;
  compact?: boolean;
}) {
  const [filter, setFilter] = useState<"all" | "todo" | "done">("todo");

  const visible = useMemo(() => {
    if (filter === "all") return tasks;
    return tasks.filter((t) => t.status === filter);
  }, [filter, tasks]);

  const remaining = tasks.filter((t) => t.status === "todo").length;

  return (
    <div className={cn("rounded-2xl border bg-card shadow-soft-sm", compact ? "p-4" : "p-5")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">Action queue</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Coach-grade tasks generated from gaps + learning plan. Ship one, snapshot, repeat.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="tabular-nums rounded-lg">
            {remaining} open
          </Badge>
          <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => {
            setFilter((f) => (f === "todo" ? "all" : "todo"));
          }}>
            <Filter className="h-4 w-4" />
            {filter === "todo" ? "Show all" : "Show open"}
          </Button>
        </div>
      </div>

      <Separator className="my-4" />

      {visible.length === 0 ? (
        <div className="rounded-xl bg-muted/40 p-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="h-4 w-4 text-primary" />
            No tasks in this view.
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            When you generate gaps/learning plan, tasks will appear here automatically.
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {visible.slice(0, compact ? 6 : 12).map((t) => (
            <button
              key={t.id}
              className={cn(
                "w-full rounded-xl border p-3 text-left hover:bg-muted/40 transition-colors",
                t.status === "done" && "opacity-70"
              )}
              onClick={() => onToggle(t)}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5">
                  {t.status === "done" ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                  ) : (
                    <Circle className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold truncate">{t.title}</div>
                    <Badge
                      variant="secondary"
                      className={cn(
                        "text-[11px]",
                        t.priority === "high" && "bg-amber-500/10 text-amber-700",
                        t.priority === "medium" && "bg-blue-500/10 text-blue-700"
                      )}
                    >
                      {t.priority}
                    </Badge>
                  </div>
                  {t.detail ? (
                    <div className="mt-1 text-xs text-muted-foreground leading-snug">
                      {t.detail}
                    </div>
                  ) : null}
                  {t.why ? (
                    <div className="mt-2 text-[11px] text-muted-foreground leading-snug">
                      <span className="font-medium text-foreground/80">Why:</span>{" "}
                      {t.why}
                    </div>
                  ) : null}
                  {t.appId && onOpenWorkspace ? (
                    <div className="mt-2">
                      <Button
                        variant="link"
                        size="sm"
                        className="h-auto p-0 text-xs"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          onOpenWorkspace(t.appId!);
                        }}
                      >
                        Open workspace
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

