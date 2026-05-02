"use client";

/**
 * A2.c — Insights dashboard page.
 *
 * Renders the three pattern_insights sections (funnel /
 * score_outcome / archetype) plus the insights_blockers panel and
 * the recommendations stream, all from a single GET /api/insights
 * round-trip.
 *
 * Per-section rendering rule: if the response shape is the
 * `{ kind: "insufficient_data", have, need }` sentinel we render an
 * encouraging empty-state copy instead of a half-built chart. This
 * matches the backend's MIN_OUTCOMES (5) gate — we never show
 * statistical claims off three data points.
 *
 * No chart library: the panels are CSS-driven (Tailwind width
 * percentages) to keep the bundle lean. Recharts/visx can replace
 * these later without API churn — the response shape is stable.
 */

import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity, AlertTriangle, BarChart3, Loader2, Target, TrendingUp,
  Users, Zap,
} from "lucide-react";

// ── Types — narrow mirrors of the backend serializer output ──────────

type InsufficientData = {
  kind: "insufficient_data";
  have: number;
  need: number;
  reason: string;
};

type FunnelStage = {
  name: string;
  count: number;
  rate_from_prior: number | null;
  rate_from_top: number | null;
};

type FunnelInsight = {
  stages: FunnelStage[];
  total_outcomes: number;
};

type ScoreBucket = {
  label: string;
  lower: number;
  upper: number;
  won: number;
  lost: number;
  win_rate: number | null;
};

type ScoreOutcomeInsight = {
  buckets: ScoreBucket[];
  cutoff_score: number | null;
  total_scored_outcomes: number;
};

type ArchetypeRow = {
  label: string;
  n: number;
  response_rate: number;
  interview_rate: number;
  offer_rate: number;
};

type ArchetypePerformance = {
  rows: ArchetypeRow[];
  excluded_for_low_n: string[];
};

type BlockerCount = {
  category: string;
  count: number;
  share: number;
  samples: string[];
};

type BlockerReport = {
  counts: BlockerCount[];
  total_rejected: number;
  total_with_reason: number;
  classified: number;
  sufficient: boolean;
};

type Recommendation = {
  code: string;
  severity: "critical" | "warning" | "info";
  title: string;
  body: string;
  metric: string | null;
};

type InsightsResponse = {
  patterns: {
    funnel: FunnelInsight | InsufficientData;
    score_outcome: ScoreOutcomeInsight | InsufficientData;
    archetype: ArchetypePerformance | InsufficientData;
    total_applications: number;
    total_outcomes: number;
  };
  blockers: BlockerReport;
  recommendations: Recommendation[];
  total_applications: number;
};

// ── Type guard ────────────────────────────────────────────────────────

function isInsufficient(v: unknown): v is InsufficientData {
  return (
    !!v && typeof v === "object" &&
    (v as { kind?: unknown }).kind === "insufficient_data"
  );
}

// ── Formatters ────────────────────────────────────────────────────────

const pct = (n: number | null | undefined): string =>
  n == null ? "—" : `${Math.round(n * 100)}%`;

const titleCase = (s: string): string =>
  s.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

// ── Empty state ───────────────────────────────────────────────────────

function InsufficientDataPanel({ data, label }: { data: InsufficientData; label: string }) {
  const remaining = Math.max(0, data.need - data.have);
  return (
    <div className="rounded-xl border border-dashed border-muted-foreground/30 bg-muted/20 p-6 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-muted">
        <BarChart3 className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium text-foreground">{label} — not enough data yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {data.have} of {data.need} closed-out applications. {remaining > 0
          ? `${remaining} more and this panel turns on.`
          : "Almost there."}
      </p>
    </div>
  );
}

// ── Funnel panel ──────────────────────────────────────────────────────

function FunnelPanel({ data }: { data: FunnelInsight }) {
  const top = data.stages[0]?.count ?? 0;
  return (
    <div className="space-y-3">
      {data.stages.map((s) => {
        const widthPct = top > 0 ? Math.max(4, (s.count / top) * 100) : 0;
        return (
          <div key={s.name}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="font-medium">{titleCase(s.name)}</span>
              <span className="text-muted-foreground">
                {s.count}
                {s.rate_from_prior != null && (
                  <span className="ml-2 text-xs">
                    ({pct(s.rate_from_prior)} from prior)
                  </span>
                )}
              </span>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all"
                style={{ width: `${widthPct}%` }}
                role="presentation"
              />
            </div>
          </div>
        );
      })}
      <p className="pt-2 text-xs text-muted-foreground">
        Based on {data.total_outcomes} applications past the draft stage.
      </p>
    </div>
  );
}

// ── Score-outcome panel ───────────────────────────────────────────────

function ScoreOutcomePanel({ data }: { data: ScoreOutcomeInsight }) {
  const maxN = Math.max(...data.buckets.map((b) => b.won + b.lost), 1);
  return (
    <div className="space-y-3">
      {data.cutoff_score != null && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-500/10 p-3 text-sm dark:border-emerald-900">
          <span className="font-medium text-emerald-700 dark:text-emerald-300">
            Win-rate crosses 50% at fit-score ≥ {data.cutoff_score.toFixed(1)}
          </span>
          <p className="mt-1 text-xs text-muted-foreground">
            Applications below this score have less than even odds — consider raising your bar.
          </p>
        </div>
      )}
      <div className="space-y-2">
        {data.buckets.map((b) => {
          const total = b.won + b.lost;
          const widthPct = total > 0 ? (total / maxN) * 100 : 4;
          const wonPct = total > 0 ? (b.won / total) * 100 : 0;
          return (
            <div key={b.label}>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium">{b.label}</span>
                <span className="text-muted-foreground">
                  {total > 0 ? `${b.won}W / ${b.lost}L · ${pct(b.win_rate)} win` : "no data"}
                </span>
              </div>
              <div
                className="relative h-3 overflow-hidden rounded-full bg-muted"
                style={{ width: `${widthPct}%` }}
              >
                <div
                  className="h-full bg-emerald-500/80"
                  style={{ width: `${wonPct}%` }}
                  role="presentation"
                />
              </div>
            </div>
          );
        })}
      </div>
      <p className="pt-1 text-xs text-muted-foreground">
        Based on {data.total_scored_outcomes} scored outcomes.
      </p>
    </div>
  );
}

// ── Archetype panel ───────────────────────────────────────────────────

function ArchetypePanel({ data }: { data: ArchetypePerformance }) {
  if (data.rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No archetype has reached the per-label minimum yet
        {data.excluded_for_low_n.length > 0 && (
          <> ({data.excluded_for_low_n.length} below threshold)</>
        )}.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {data.rows.map((row) => (
        <div key={row.label} className="rounded-lg border border-border/40 p-3">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-sm font-medium">{titleCase(row.label)}</span>
            <span className="text-xs text-muted-foreground">{row.n} apps</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-muted-foreground">Response</span>
              <div className="font-semibold">{pct(row.response_rate)}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Interview</span>
              <div className="font-semibold">{pct(row.interview_rate)}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Offer</span>
              <div className="font-semibold text-emerald-600 dark:text-emerald-400">
                {pct(row.offer_rate)}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Blockers panel ────────────────────────────────────────────────────

function BlockersPanel({ data }: { data: BlockerReport }) {
  if (!data.sufficient) {
    return (
      <InsufficientDataPanel
        data={{
          kind: "insufficient_data",
          have: data.total_rejected,
          need: 5,
          reason: "min_blocker_outcomes_not_met",
        }}
        label="Blocker patterns"
      />
    );
  }
  if (data.counts.length === 0) {
    return <p className="text-sm text-muted-foreground">No rejection reasons logged yet.</p>;
  }
  return (
    <div className="space-y-3">
      {data.counts.map((c) => (
        <div key={c.category} className="rounded-lg border border-border/40 p-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium">{titleCase(c.category)}</span>
            <Badge variant="secondary" className="text-xs">
              {c.count} · {pct(c.share)}
            </Badge>
          </div>
          {c.samples.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs italic text-muted-foreground">
              {c.samples.map((s, i) => (
                <li key={i}>“{s}”</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Recommendations stream ────────────────────────────────────────────

const SEVERITY_STYLES: Record<Recommendation["severity"], string> = {
  critical: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

function RecommendationsPanel({ items }: { items: Recommendation[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No recommendations yet — keep going. Patterns sharpen with every closed application.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {items.map((r) => (
        <div
          key={r.code}
          className={`rounded-lg border p-4 ${SEVERITY_STYLES[r.severity]}`}
        >
          <div className="mb-1 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm font-semibold">{r.title}</span>
            {r.metric && (
              <Badge variant="outline" className="ml-auto text-xs">{r.metric}</Badge>
            )}
          </div>
          <p className="text-xs leading-relaxed text-foreground/80">{r.body}</p>
        </div>
      ))}
    </div>
  );
}

// ── Section wrapper ───────────────────────────────────────────────────

function Section({
  title, icon: Icon, children,
}: { title: string; icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-border/40 bg-card p-5 shadow-sm"
    >
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      {children}
    </motion.section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────

export default function InsightsPage() {
  const { session: authSession } = useAuth();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authSession?.access_token) return;
    api.setToken(authSession.access_token);
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const resp = await api.insights.get();
        if (!cancelled) setData(resp as InsightsResponse);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load insights");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authSession?.access_token]);

  const totalApps = data?.total_applications ?? 0;
  const headerSubtitle = useMemo(() => {
    if (loading) return "Loading…";
    if (error) return error;
    if (totalApps === 0) return "Apply to a few roles to unlock pattern detection.";
    return `Patterns mined from ${totalApps} application${totalApps === 1 ? "" : "s"}.`;
  }, [loading, error, totalApps]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-glow-sm">
          <Activity className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Insights</h1>
          <p className="text-sm text-muted-foreground">{headerSubtitle}</p>
        </div>
      </div>

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
          <Loader2 className="mr-2 inline h-4 w-4" />
          {error}
          <Button
            size="sm"
            variant="outline"
            className="ml-3"
            onClick={() => window.location.reload()}
          >
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && data && (
        <>
          <Section title="Application funnel" icon={Target}>
            {isInsufficient(data.patterns.funnel)
              ? <InsufficientDataPanel data={data.patterns.funnel} label="Funnel" />
              : <FunnelPanel data={data.patterns.funnel} />}
          </Section>

          <Section title="Score × outcome" icon={TrendingUp}>
            {isInsufficient(data.patterns.score_outcome)
              ? <InsufficientDataPanel data={data.patterns.score_outcome} label="Score correlation" />
              : <ScoreOutcomePanel data={data.patterns.score_outcome} />}
          </Section>

          <Section title="Archetype performance" icon={Users}>
            {isInsufficient(data.patterns.archetype)
              ? <InsufficientDataPanel data={data.patterns.archetype} label="Archetype rates" />
              : <ArchetypePanel data={data.patterns.archetype} />}
          </Section>

          <Section title="Blocker patterns" icon={AlertTriangle}>
            <BlockersPanel data={data.blockers} />
          </Section>

          <Section title="Recommendations" icon={Zap}>
            <RecommendationsPanel items={data.recommendations} />
          </Section>
        </>
      )}
    </div>
  );
}
