---
title: Performance Context
last_synced: 2026-05-08
watch_paths:
  - k6
  - infra/observability
  - backend/app/services/usage_guard.py
  - ai_engine/cache.py
  - ai_engine/model_router.py
canonical_sources:
  - docs/SLO.md
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#10-slo-and-cost
update_when:
  - SLO targets change
  - a new caching layer is added
  - a new dynamic model selection rule is introduced
  - the per-org cost cap changes
  - k6 scenarios change
  - frontend bundle budgets change
---

# Performance Context

> Performance is a feature with an SLO. We measure 4 things and let the
> rest float. Optimization is justified by a tracked metric, not a hunch.

---

## TL;DR — 10 lines

1. **Four production SLOs** (canonical in [docs/SLO.md](../docs/SLO.md)):
   generation success ≥ 99.5%; generation p95 wall-clock ≤ 90s; API
   availability ≥ 99.95%; LLM cost ≤ per-org daily $ budget.
2. **Latency budget per phase** (rough): Recon ≤ 12s, Atlas ≤ 8s, Cipher
   ≤ 18s, Quill ≤ 30s (parallel), Forge ≤ 12s (optional), Sentinel ≤ 10s,
   Nova ≤ 4s. Sum ≈ 94s; p95 target 90s assumes Forge skipped.
3. **Cost levers (in priority order):** prompt cache hit rate, dynamic
   model selection (router downshifts to flash when input small + task
   simple), batch inference at off-peak.
4. **Rate limits per org per minute** (default Pro tier):
   `POST /generate/jobs` 6, `POST /aim/lookup` 30, `GET /aim/...` 120.
   Per-tier overrides in `usage_quotas`.
5. **Cost cap per org per day** (P0-4): default $50 (Pro), $200 (Team),
   $1000 (Enterprise). Hit cap → 402 `billing.cap_exceeded`.
6. **k6 scenarios** under `k6/scenarios/` exercise burst, sustained, and
   SSE soak. Run against staging.
7. **Frontend perf budget**: LCP ≤ 2.5s on 4G, CLS ≤ 0.1, TTI ≤ 3.5s.
   Initial JS payload ≤ 200kB gz on dashboard route.
8. **DB perf:** RLS policies indexed on `org_id`. Heavy reads
   (`document_catalog`, `aim_source`) backed by composite indexes
   (org_id, updated_at desc).
9. **Pipeline backpressure**: per-org concurrency cap; per-cell global
   cap; queue depth alert at 80% of cap.
10. **Hot path optimization is OFF-LIMITS without a profile.** No
    speculative caching, no premature index, no microopt without a
    measured win.

---

## SLOs

Canonical in [docs/SLO.md](../docs/SLO.md).

| SLO | Target | Window | Error budget | Burn-rate alert |
|---|---|---|---|---|
| Generation success rate | ≥ 99.5% | 28 days | 0.5% | 14.4× burn over 1h pages |
| Generation p95 wall-clock | ≤ 90s | rolling 7d | n/a | p95 > 90s for 30m pages |
| API availability | ≥ 99.95% | 28 days | 0.05% | 5xx rate > 1% for 5m pages |
| LLM cost vs budget | ≤ per-org daily cap | rolling 24h | n/a | per-org cap hit ≥ 5×/day pages |

Multi-window multi-burn-rate (MWMBR) alerting per SRE Workbook.

---

## Per-phase latency budgets

| Phase | Budget | Why |
|---|---|---|
| Recon | 12s | 3 chains in parallel; biggest is CompanyIntel (multi-source RAG) |
| Atlas | 8s | one chain (Benchmark); reasonably bounded |
| Cipher | 18s | gap analysis + evidence ledger; both data-heavy |
| Quill | 30s | drafting CV + cover + statement in parallel; longest output |
| Forge | 12s (optional) | portfolio + PPT + LinkedIn; only if user asked |
| Sentinel | 10s | factcheck + ATS scan; cheaper short prompts |
| Nova | 4s | assembly + persistence; mostly DB |

Summing serially: ≈ 94s. Parallel paths within phase plus Forge being
optional give us p95 ≤ 90s headroom.

A single chain over budget is fine; phase-level budget is what the SLO
enforces. The orchestrator emits `stage.duration_ms` per phase; Grafana
alerts on p95 budget breach.

---

## Cost levers

Cost is dominated by Quill drafts and Cipher evidence work. Levers:

1. **Prompt cache hit rate.** Two-tier (LRU + Redis). Hit rate metric:
   `ai.cache.hit_rate{tier=lru|redis}`. Stable system prompts and the
   benchmark phase have high cacheability (same role profile → same
   benchmark).
2. **Dynamic model selection.** Router downshifts to `gemini-2.5-flash`
   for `CLASSIFY` / `PARSE` / `SCORE` profiles (see
   [AI_CONTEXT.md](AI_CONTEXT.md)). Forced upshift via `task_profile`
   override on heavy chains.
3. **Batch inference (Stage B).** Group chain calls with similar
   prompts; submit as batch jobs at off-peak (Gemini batch API). Saves
   ~ 50% on per-token cost; only viable for non-realtime chains
   (eval, archive, RAG re-embed).
4. **Cost projection × 1.10** (already in place). Pre-flight stops calls
   that would breach the org's daily cap.

---

## Rate limits and concurrency caps

Per-route per-org rate limits via slowapi (Redis-backed). Defaults:

| Route | Free | Pro | Team | Enterprise |
|---|---|---|---|---|
| `POST /generate/jobs` | 1/min | 6/min | 20/min | 100/min |
| `POST /aim/lookup` | 5/min | 30/min | 120/min | 600/min |
| `GET /aim/...` | 30/min | 120/min | 600/min | 3000/min |
| `POST /interview/sessions` | 1/min | 6/min | 20/min | 100/min |
| `POST /export/...` | 5/min | 30/min | 120/min | 600/min |

Concurrent in-flight generations per org:

| Tier | Max in-flight |
|---|---|
| Free | 1 |
| Pro | 3 |
| Team | 10 |
| Enterprise | 50 |

Beyond the cap → request returns 202 with a queued `job_id` and a
projected start time. The frontend shows a "queued" state.

Per-cell global cap (configured per cell): protects shared infra. When
hit, 503 `pipeline.unavailable` is returned immediately rather than
queuing further.

---

## Database performance

- All RLS-filtered tables indexed on `(org_id, ...)`. The leading column
  must be `org_id` for RLS planner to choose the index.
- Hot read patterns:
  - `document_catalog` indexed on `(org_id, updated_at desc)`.
  - `applications` indexed on `(org_id, status, updated_at desc)`.
  - `ai_invocations` partitioned monthly; recent partition has a
    `(org_id, created_at desc)` index for the cost rollup.
- Heavy aggregates run as materialized views refreshed on schedule
  (`org_cost_hourly`, `pipeline_funnel_daily`).
- Long queries (> 5s) tagged with `application_name = 'long-read'` so
  pgbouncer can route to a separate pool.
- `EXPLAIN ANALYZE` is mandatory for any new query > 100ms.

---

## Frontend perf budgets

| Metric | Target | How measured |
|---|---|---|
| LCP | ≤ 2.5s on 4G | Lighthouse CI per PR |
| CLS | ≤ 0.1 | Lighthouse CI |
| TTI | ≤ 3.5s | Lighthouse CI |
| Initial JS (dashboard) | ≤ 200kB gz | bundle analyzer |
| SSE first event | ≤ 1s after `connect` | client-side metric |
| Stream token jitter | < 200ms p95 | client-side metric |

Code-splitting via Next.js dynamic imports. Heavy components (TipTap,
PDF preview) are dynamically imported on user interaction.

Image optimization: Next.js `<Image>` everywhere; OG images
pre-generated.

---

## SSE streaming

`GET /api/generate/agentic-stream/{job_id}` is the primary stream
surface. Performance constraints:

- Heartbeat every 15s.
- Per-event size soft cap 64kB; hard cap 256kB (split into chunks).
- Token streaming: `stage.token` events flushed at most every 50ms (rate
  limited at the emitter to avoid render thrash).
- Reconnect: client retries with exponential backoff and `Last-Event-ID`
  header; server resumes from offset (P1-3 SHIPPED — m9-pr34/35).

---

## k6 load tests

`k6/scenarios/`:

| Scenario | Pattern | Pass criteria |
|---|---|---|
| `gen_burst.js` | 0 → 50 RPS over 30s, hold 5m | p95 latency for `POST /generate/jobs` < 500ms; error rate < 1% |
| `gen_sustained.js` | 30 RPS for 30m | per-phase p95 within budget; cost rollup grows linearly |
| `aim_lookup.js` | 200 RPS for 10m | p95 < 200ms; cache hit rate > 70% |
| `sse_soak.js` | 100 concurrent connections for 30m | zero dropped connections; jitter p95 < 200ms |
| `dlq_replay.js` | 10 RPS replays | no double-write; idempotency_keys deduplicates |

Run via `make load-test SCENARIO=gen_burst`.

---

## Profiling

Backend: `py-spy` attached to a worker for ad-hoc profiles. Flame graphs
live in `docs/_archive/profiles/` for historical reference.

Frontend: Chrome DevTools Performance + React DevTools Profiler. No
React 18 strict-mode-related double-renders are tolerated in production
code paths (TODO marker if found).

DB: `pg_stat_statements` enabled. Top-20 queries reviewed monthly.

---

## When to invest in performance

Order of operations:

1. **Measure** first. If there is no metric showing the regression,
   there is no regression.
2. **Identify the dominant cost.** Per Amdahl, optimize the largest
   fraction.
3. **Choose a lever already in the toolbox** (cache, batch, route to
   cheaper model).
4. **Only if the toolbox is exhausted** introduce a new lever — and when
   you do, make it observable so the next person can tell whether it
   helped.
5. **Update SLOs** if a new lever changes the steady-state shape.

---

## What "good performance" looks like in this repo

- [ ] Change does not regress any of the 4 SLOs.
- [ ] New endpoint has a rate limit and a per-org concurrency understood.
- [ ] New chain has a per-call cost projection within phase budget.
- [ ] New DB query has an index for the RLS-filtered access path.
- [ ] New SSE event obeys the 50ms / 64kB / 15s constraints.
- [ ] New frontend code respects bundle budget; heavy bits are
      dynamically imported.
- [ ] Any optimization PR cites the metric it moves and includes a
      before/after dashboard link.
