import Link from "next/link";
import { ArrowRight, Bot, Clock3, FileText, Sparkles, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ApplicationDoc, ModuleStatus } from "@/lib/firestore/models";

type ReadyState = "ready_to_apply" | "ready_for_review" | "generating" | "queued";

type InboxItem = {
  app: ApplicationDoc;
  title: string;
  company: string;
  generatedCount: number;
  fitPercent: number;
  isAutoPrepared: boolean;
  state: ReadyState;
};

const STATE_META: Record<ReadyState, { label: string; accent: string; description: string }> = {
  ready_to_apply: {
    label: "Ready now",
    accent: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    description: "Core application docs are drafted and waiting for your review.",
  },
  ready_for_review: {
    label: "Review draft",
    accent: "bg-sky-500/10 text-sky-500 border-sky-500/20",
    description: "Support artifacts are ready and the workspace is worth reviewing next.",
  },
  generating: {
    label: "Generating",
    accent: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    description: "Generation is still running, but this workspace is already in the queue.",
  },
  queued: {
    label: "Queued",
    accent: "bg-slate-500/10 text-slate-500 border-slate-500/20",
    description: "The watchlist hit was promoted into a workspace and is waiting to be processed.",
  },
};

function generatedDocumentCount(app: ApplicationDoc): number {
  const core = [app.cvHtml, app.coverLetterHtml, app.personalStatementHtml, app.portfolioHtml].filter(Boolean).length;
  const extra = Object.values(app.generatedDocuments || {}).filter(Boolean).length;
  return core + extra;
}

function normalizedFitPercent(app: ApplicationDoc): number {
  const raw = Number(app.scores?.fit ?? app.confirmedFacts?.auto_prep?.fit_score ?? app.scores?.match ?? 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return raw <= 5 ? Math.round(raw * 20) : Math.round(raw);
}

function moduleStates(app: ApplicationDoc): ModuleStatus[] {
  return Object.values(app.modules || {}) as ModuleStatus[];
}

function classify(app: ApplicationDoc): InboxItem | null {
  if (app.status !== "draft") return null;

  const title = app.title || app.confirmedFacts?.jobTitle || app.confirmedFacts?.job_title || "Untitled role";
  const company = app.confirmedFacts?.company || "Tracked company";
  const generatedCount = generatedDocumentCount(app);
  const fitPercent = normalizedFitPercent(app);
  const isAutoPrepared = app.confirmedFacts?.source === "tracked_company_auto_prep" || Boolean(app.confirmedFacts?.auto_prep);
  const states = moduleStates(app);
  const isGenerating = states.some((module) => module?.state === "generating");
  const isQueued = states.some((module) => module?.state === "queued");
  const hasReviewSignals = Boolean(app.scorecard || app.benchmark || app.gaps);
  const hasPrimaryDocs = Boolean(app.cvHtml || app.resumeHtml) && Boolean(
    app.coverLetterHtml || app.personalStatementHtml || app.portfolioHtml || Object.values(app.generatedDocuments || {}).some(Boolean),
  );

  let state: ReadyState | null = null;
  if (hasPrimaryDocs && hasReviewSignals) {
    state = "ready_to_apply";
  } else if (generatedCount > 0 || hasReviewSignals) {
    state = "ready_for_review";
  } else if (isGenerating) {
    state = "generating";
  } else if (isQueued || isAutoPrepared) {
    state = "queued";
  }

  if (!state) return null;

  return {
    app,
    title,
    company,
    generatedCount,
    fitPercent,
    isAutoPrepared,
    state,
  };
}

function sortItems(left: InboxItem, right: InboxItem): number {
  const stateRank: Record<ReadyState, number> = {
    ready_to_apply: 0,
    ready_for_review: 1,
    generating: 2,
    queued: 3,
  };
  return (
    stateRank[left.state] - stateRank[right.state]
    || Number(right.isAutoPrepared) - Number(left.isAutoPrepared)
    || right.generatedCount - left.generatedCount
    || right.fitPercent - left.fitPercent
    || right.app.updatedAt - left.app.updatedAt
  );
}

export function ReadyToApply({ apps }: { apps: ApplicationDoc[] }) {
  if (!apps.length) return null;

  const classified = apps.map(classify).filter((item): item is InboxItem => item !== null).sort(sortItems);
  if (!classified.length) return null;

  const visible = classified.slice(0, 5);
  const readyCount = classified.filter((item) => item.state === "ready_to_apply" || item.state === "ready_for_review").length;
  const inFlightCount = classified.filter((item) => item.state === "generating" || item.state === "queued").length;

  return (
    <section className="rounded-3xl border bg-card p-5 shadow-soft-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Ready to apply</h2>
              <p className="text-xs text-muted-foreground">
                Draft workspaces that are already waiting for your morning review.
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-xl border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <Bot className="h-3.5 w-3.5 text-primary" />
          {readyCount} ready now{inFlightCount > 0 ? ` · ${inFlightCount} still generating` : ""}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {visible.map((item) => {
          const meta = STATE_META[item.state];
          return (
            <Link
              key={item.app.id}
              href={`/applications/${item.app.id}`}
              className="group rounded-2xl border bg-background/60 p-4 transition-all duration-300 hover:border-primary/20 hover:shadow-soft-sm hover:-translate-y-0.5"
            >
              <div className="flex items-center justify-between gap-2">
                <Badge variant="secondary" className={cn("border", meta.accent)}>
                  {meta.label}
                </Badge>
                {item.isAutoPrepared && (
                  <Badge variant="secondary" className="border-primary/20 bg-primary/10 text-primary">
                    Watchlist
                  </Badge>
                )}
              </div>

              <div className="mt-3 min-h-[64px]">
                <p className="text-sm font-semibold transition-colors group-hover:text-primary">{item.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{item.company}</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{meta.description}</p>
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  {item.generatedCount} doc{item.generatedCount === 1 ? "" : "s"}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Target className="h-3 w-3" />
                  {item.fitPercent > 0 ? `${item.fitPercent}% fit` : "Freshly scored"}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Clock3 className="h-3 w-3" />
                  Updated recently
                </span>
                <span className="inline-flex items-center gap-1 text-primary">
                  Open workspace <ArrowRight className="h-3 w-3" />
                </span>
              </div>
            </Link>
          );
        })}
      </div>

      <div className="mt-4 flex justify-end">
        <Button asChild variant="outline" size="sm" className="rounded-xl text-xs">
          <Link href="/dashboard">
            Review inbox <ArrowRight className="ml-1.5 h-3 w-3" />
          </Link>
        </Button>
      </div>
    </section>
  );
}
