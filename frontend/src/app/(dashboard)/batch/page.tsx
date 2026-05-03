"use client";

/**
 * B0.frontend — Batch generate page.
 *
 * Two-step paste-then-score flow:
 *   1. User pastes URLs → "Preview" calls POST /generate/batch/plan.
 *      Instant pure-fn validation: shows "X accepted / Y rejected"
 *      with per-row reason chips (over_cap / empty / invalid_url /
 *      duplicate) BEFORE the user commits to the slow scoring step.
 *   2. User clicks "Score N URLs" → POST /generate/batch/score.
 *      Renders three buckets: ranked (>= threshold, sorted desc),
 *      below_threshold, failed.
 *
 * The backend default scorer is currently a stub that returns
 * `error: "scorer_not_configured"` per row.  This page renders that
 * gracefully — the Failed bucket carries the typed error so a
 * misconfigured deploy is visible per-row instead of silently
 * showing zero scores.
 *
 * No persistence yet (B0.persist is the next slice) — clicking
 * "Score" is read-only and idempotent; refresh the page and the
 * results vanish.  This is intentional for the preview flow.
 */

import React, { useMemo, useState } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle, CheckCircle2, ListChecks, Loader2, Save, Sparkles,
  TrendingDown, XCircle,
} from "lucide-react";

// ── Response types (mirror backend serializers) ─────────────────────

type BatchEntry = {
  raw_url: string;
  canonical_url: string;
  ats_key: [string, string, string] | null;
};

type BatchReject = {
  raw_url: string;
  reason: "empty" | "invalid_url" | "duplicate" | "over_cap";
};

type BatchPlan = {
  accepted: BatchEntry[];
  rejected: BatchReject[];
  summary: {
    accepted_count: number;
    rejected_count: number;
    max_urls: number;
    is_empty: boolean;
  };
};

type PlanResponse = BatchPlan & { min_fit_score: number };

type ScoringResult = {
  canonical_url: string;
  fit_score: number | null;
  error: string | null;
  title: string | null;
  company: string | null;
};

type ScoreResponse = {
  plan: BatchPlan;
  scored: {
    ranked: ScoringResult[];
    below_threshold: ScoringResult[];
    failed: ScoringResult[];
    summary: {
      ranked_count: number;
      below_threshold_count: number;
      failed_count: number;
    };
  };
  min_fit_score: number;
};

type PersistedRow = { canonical_url: string; application_id: string };

type CommitResponse = ScoreResponse & {
  persisted: {
    batch_id: string;
    inserted: PersistedRow[];
    inserted_count: number;
    skipped: PersistedRow[];
    skipped_count: number;
  };
};

// ── Helpers ──────────────────────────────────────────────────────────

const REASON_COPY: Record<BatchReject["reason"], string> = {
  empty: "Empty entry",
  invalid_url: "Not a valid URL",
  duplicate: "Duplicate of an earlier URL",
  over_cap: "Past the per-batch cap",
};

const REASON_TONE: Record<BatchReject["reason"], string> = {
  empty: "bg-slate-100 text-slate-700 border-slate-200",
  invalid_url: "bg-rose-50 text-rose-700 border-rose-200",
  duplicate: "bg-amber-50 text-amber-700 border-amber-200",
  over_cap: "bg-sky-50 text-sky-700 border-sky-200",
};

function splitUrls(raw: string): string[] {
  // Split on newlines, commas, and whitespace runs; trim each.
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function describeError(code: string): string {
  if (code === "scorer_not_configured") {
    return "Scoring backend not configured yet (stub). Wiring lands in B0.scorer.";
  }
  if (code.startsWith("scorer_bug:")) {
    return `Scorer crashed: ${code.slice("scorer_bug:".length)}`;
  }
  if (code === "scorer_bad_return") return "Scorer returned an invalid value.";
  if (code === "scorer_url_mismatch") return "Scorer returned a different URL.";
  return code;
}

function formatScore(s: number | null): string {
  if (s == null) return "—";
  return s.toFixed(2);
}

// ── Page ────────────────────────────────────────────────────────────

export default function BatchGeneratePage() {
  const { session } = useAuth();
  const [raw, setRaw] = useState("");
  const [minFitScore, setMinFitScore] = useState(3.0);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [scored, setScored] = useState<ScoreResponse | null>(null);
  const [committed, setCommitted] = useState<CommitResponse["persisted"] | null>(null);
  const [planning, setPlanning] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const urls = useMemo(() => splitUrls(raw), [raw]);

  const setToken = () => {
    if (session?.access_token) api.setToken(session.access_token);
  };

  async function handlePreview() {
    setErr(null);
    setScored(null);
    setCommitted(null);
    if (urls.length === 0) {
      setPlan(null);
      return;
    }
    setPlanning(true);
    try {
      setToken();
      const res = (await api.batchGenerate.plan(urls, minFitScore)) as PlanResponse;
      setPlan(res);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to validate URLs");
    } finally {
      setPlanning(false);
    }
  }

  async function handleScore() {
    if (!plan || plan.summary.is_empty) return;
    setErr(null);
    setCommitted(null);
    setScoring(true);
    try {
      setToken();
      const res = (await api.batchGenerate.score(urls, {
        min_fit_score: minFitScore,
      })) as ScoreResponse;
      setScored(res);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to score URLs");
    } finally {
      setScoring(false);
    }
  }

  /**
   * Save-to-Drafts: re-runs plan + score + persist in one call.
   * We pass the same `urls` (NOT scored.scored.ranked URLs) so the
   * server applies its own min_fit_score filter — keeps the source of
   * truth on the backend and lets the user adjust the slider after
   * scoring without forcing a re-score round-trip just to re-rank.
   * Idempotent: backend pre-queries dedup_keys and surfaces existing
   * Drafts in `persisted.skipped` instead of inserting duplicates.
   */
  async function handleCommit() {
    if (!scored || scored.scored.ranked.length === 0) return;
    setErr(null);
    setCommitting(true);
    try {
      setToken();
      const res = (await api.batchGenerate.commit(urls, {
        min_fit_score: minFitScore,
      })) as CommitResponse;
      setCommitted(res.persisted);
      // Refresh the scored bucket too — server-side ranking is the
      // source of truth and the min_fit_score may have changed.
      setScored({ plan: res.plan, scored: res.scored, min_fit_score: res.min_fit_score });
    } catch (e: any) {
      setErr(e?.message ?? "Failed to save drafts");
    } finally {
      setCommitting(false);
    }
  }

  function handleClear() {
    setRaw("");
    setPlan(null);
    setScored(null);
    setCommitted(null);
    setErr(null);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Batch generate
        </h1>
        <p className="text-sm text-slate-600">
          Paste up to 25 job-posting URLs. Preview which ones we'll keep,
          then score them against your profile in one shot.
        </p>
      </header>

      {/* Paste input */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <label
          htmlFor="urls"
          className="block text-sm font-medium text-slate-700"
        >
          Job posting URLs
        </label>
        <textarea
          id="urls"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder={"https://boards.greenhouse.io/acme/jobs/101\nhttps://jobs.lever.co/foo/abc-123"}
          rows={8}
          className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none"
          disabled={planning || scoring}
        />
        <p className="mt-1 text-xs text-slate-500">
          One URL per line, or comma-separated. {urls.length} entr{urls.length === 1 ? "y" : "ies"} detected.
        </p>

        <div className="mt-4 flex items-end gap-4">
          <label className="flex flex-col text-xs font-medium text-slate-700">
            Minimum fit score (0.0 – 5.0)
            <input
              type="number"
              step="0.1"
              min={0}
              max={5}
              value={minFitScore}
              onChange={(e) => setMinFitScore(parseFloat(e.target.value) || 0)}
              className="mt-1 w-32 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm"
              disabled={planning || scoring}
            />
          </label>

          <div className="ml-auto flex gap-2">
            <Button
              variant="outline"
              onClick={handleClear}
              disabled={planning || scoring || raw.length === 0}
            >
              Clear
            </Button>
            <Button
              onClick={handlePreview}
              disabled={planning || scoring || urls.length === 0}
            >
              {planning ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Validating…
                </>
              ) : (
                <>
                  <ListChecks className="mr-2 h-4 w-4" /> Preview
                </>
              )}
            </Button>
          </div>
        </div>
      </section>

      {err && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{err}</span>
        </div>
      )}

      {/* Plan preview */}
      {plan && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Preview</h2>
            <div className="flex items-center gap-3 text-sm">
              <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                {plan.summary.accepted_count} accepted
              </Badge>
              <Badge className="bg-rose-100 text-rose-800 hover:bg-rose-100">
                {plan.summary.rejected_count} rejected
              </Badge>
              <span className="text-xs text-slate-500">
                cap: {plan.summary.max_urls}
              </span>
            </div>
          </div>

          {plan.accepted.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                Accepted ({plan.accepted.length})
              </div>
              <ul className="divide-y divide-slate-100">
                {plan.accepted.map((e, i) => (
                  <li key={i} className="flex items-center justify-between py-2 text-sm">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-mono text-xs text-slate-700">
                        {e.canonical_url}
                      </div>
                      {e.ats_key && (
                        <div className="mt-0.5 text-xs text-slate-500">
                          {e.ats_key[0]} · {e.ats_key[1]} · {e.ats_key[2]}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {plan.rejected.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                <XCircle className="h-4 w-4 text-rose-600" />
                Rejected ({plan.rejected.length})
              </div>
              <ul className="space-y-2">
                {plan.rejected.map((r, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 text-sm">
                    <div className="min-w-0 flex-1 truncate font-mono text-xs text-slate-600">
                      {r.raw_url || <em className="text-slate-400">(blank)</em>}
                    </div>
                    <span
                      className={`flex-shrink-0 rounded-md border px-2 py-0.5 text-xs ${REASON_TONE[r.reason]}`}
                      title={REASON_COPY[r.reason]}
                    >
                      {r.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {plan.accepted.length > 0 && (
            <div className="flex justify-end">
              <Button onClick={handleScore} disabled={scoring}>
                {scoring ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Scoring…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Score {plan.accepted.length} URL{plan.accepted.length === 1 ? "" : "s"}
                  </>
                )}
              </Button>
            </div>
          )}
        </section>
      )}

      {/* Scored buckets */}
      {scored && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Scored</h2>
            <div className="flex items-center gap-2 text-sm">
              <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                {scored.scored.summary.ranked_count} ranked
              </Badge>
              <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">
                {scored.scored.summary.below_threshold_count} below
              </Badge>
              <Badge className="bg-rose-100 text-rose-800 hover:bg-rose-100">
                {scored.scored.summary.failed_count} failed
              </Badge>
            </div>
          </div>

          <ScoredBucket
            title="Ranked"
            icon={<Sparkles className="h-4 w-4 text-emerald-600" />}
            rows={scored.scored.ranked}
            empty="No URLs cleared the minimum fit score."
            tone="emerald"
          />
          <ScoredBucket
            title={`Below threshold (< ${scored.min_fit_score.toFixed(1)})`}
            icon={<TrendingDown className="h-4 w-4 text-amber-600" />}
            rows={scored.scored.below_threshold}
            empty="None — every scored URL met the threshold."
            tone="amber"
          />
          <ScoredBucket
            title="Failed"
            icon={<XCircle className="h-4 w-4 text-rose-600" />}
            rows={scored.scored.failed}
            empty="No scoring failures."
            tone="rose"
            showError
          />

          {/* Save-to-Drafts: only meaningful when there's at least one
              ranked URL (below_threshold + failed never persist). */}
          {scored.scored.ranked.length > 0 && (
            <div className="flex items-center justify-end gap-3">
              {committed && (
                <span
                  data-testid="batch-commit-toast"
                  className="text-sm text-slate-600"
                >
                  Saved {committed.inserted_count} draft
                  {committed.inserted_count === 1 ? "" : "s"}
                  {committed.skipped_count > 0 ? (
                    <>
                      {" · "}
                      <span className="text-amber-700">
                        {committed.skipped_count} already in your Drafts
                      </span>
                    </>
                  ) : null}
                </span>
              )}
              <Button
                onClick={handleCommit}
                disabled={committing || scoring}
                data-testid="batch-commit-button"
              >
                {committing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving…
                  </>
                ) : (
                  <>
                    <Save className="mr-2 h-4 w-4" />
                    Save {scored.scored.ranked.length} to Drafts
                  </>
                )}
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ── Scored bucket panel ─────────────────────────────────────────────

function ScoredBucket({
  title,
  icon,
  rows,
  empty,
  tone,
  showError = false,
}: {
  title: string;
  icon: React.ReactNode;
  rows: ScoringResult[];
  empty: string;
  tone: "emerald" | "amber" | "rose";
  showError?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
        {icon}
        {title} ({rows.length})
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <li key={i} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-xs text-slate-700">
                  {r.canonical_url}
                </div>
                {(r.title || r.company) && (
                  <div className="mt-0.5 text-xs text-slate-600">
                    {r.title}
                    {r.title && r.company ? " · " : ""}
                    {r.company}
                  </div>
                )}
                {showError && r.error && (
                  <div className="mt-0.5 text-xs text-rose-600">
                    {describeError(r.error)}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0 text-right">
                <div
                  className={`text-base font-semibold ${
                    tone === "emerald"
                      ? "text-emerald-700"
                      : tone === "amber"
                      ? "text-amber-700"
                      : "text-rose-700"
                  }`}
                >
                  {formatScore(r.fit_score)}
                </div>
                <div className="text-xs text-slate-500">/ 5.0</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
