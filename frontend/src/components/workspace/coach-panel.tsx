"use client";

import { Lightbulb, ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type CoachAction = {
  kind: "fix" | "write" | "collect" | "review";
  title: string;
  why: string;
  cta: string;
  onClick?: () => void;
};

export function CoachPanel({
  actions = [],
  statusLine,
}: {
  actions?: CoachAction[];
  statusLine?: string;
}) {
  return (
    <aside className="sticky top-28 h-[calc(100vh-7rem)]">
      <div className="rounded-2xl border bg-card p-4 shadow-soft-sm">
        <div className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-violet-600 text-white flex items-center justify-center">
            <Lightbulb className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Coach panel</div>
            <div className="text-xs text-muted-foreground truncate">
              {statusLine || "Explainable, action-based guidance."}
            </div>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {actions.length === 0 ? (
            <div className="rounded-xl border bg-muted/30 p-3">
              <div className="text-sm font-medium">No actions right now.</div>
              <div className="mt-1 text-xs text-muted-foreground">
                When gaps or tasks appear, you’ll see next-best steps here.
              </div>
            </div>
          ) : (
            actions.slice(0, 3).map((a, idx) => (
              <div key={`${a.kind}:${idx}`} className="rounded-xl border p-3">
                <div className="flex items-start gap-2">
                  <div
                    className={cn(
                      "mt-0.5 h-6 w-6 rounded-md flex items-center justify-center",
                      a.kind === "fix" && "bg-amber-500/10 text-amber-700",
                      a.kind === "collect" && "bg-violet-500/10 text-violet-700",
                      a.kind === "write" && "bg-blue-500/10 text-blue-700",
                      a.kind === "review" && "bg-slate-500/10 text-slate-700"
                    )}
                  >
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold leading-snug">{a.title}</div>
                    <div className="mt-1 text-xs text-muted-foreground leading-snug">
                      {a.why}
                    </div>
                    <div className="mt-3">
                      <Button
                        size="sm"
                        className="w-full gap-2 rounded-xl"
                        onClick={a.onClick}
                        disabled={!a.onClick}
                      >
                        {a.cta}
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-3">
          <div className="text-xs font-semibold text-primary">Coach principle</div>
          <div className="mt-1 text-xs text-muted-foreground leading-snug">
            Don’t “spray keywords”. Each keyword must be backed by evidence and tied to an outcome.
          </div>
        </div>
      </div>
    </aside>
  );
}

