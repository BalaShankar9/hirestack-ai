# ADR-0034: `ai_invocations` flight recorder schema

**Status:** Accepted 2026-05-08
**Date:** 2026-05-08
**Deciders:** @BalaShankar9
**Context tags:** observability | ai-runtime | cost | data

---

## 1 · Context

After ADR-0031 added Anthropic as a cascade-tail provider (`m7-pr28` shipped 2026-05-08),
we need per-call attribution that survives across providers, models, and cascade
positions. Today the only persistent record of AI usage is:

* `ai_generation_usage_daily` and `ai_platform_spend_daily` (per-user / per-day
  aggregates — no model, no outcome breakdown — see
  [`20260420300000_usage_guard_tables.sql`](../../supabase/migrations/20260420300000_usage_guard_tables.sql)).
* The structured "cost log" line emitted by `_track_usage` in
  [`ai_engine/client.py`](../../ai_engine/client.py) — which is forward-only
  log stream, not queryable, and is only emitted on **success**.

Failure cases (5xx, quota exhaustion, circuit-breaker open, JSON-validation
failure) leave **no row** anywhere. That blocks every chaos-drill verification
question we're going to ask post-`m7-pr28`:
"how often does Gemini's cascade actually exhaust before hitting Anthropic?",
"what fraction of `aim_recon` calls produce an `outcome=cascade_failover`?",
"is the new circuit-breaker firing in production?". We can't answer those
without one row per LLM call, success **or** failure.

This ADR introduces a single, flat, forward-only `ai_invocations` table
written by a best-effort recorder. No backfill from logs. No partitioning at
launch (deferred — see §4). Strict no-PII: prompt body is hashed, not stored.

## 2 · Decision

We will create `public.ai_invocations` (single non-partitioned table at launch),
write one row per terminal LLM call (success **or** failure) from a new
`AIInvocationsRecorder` in `ai_engine/observability/ai_invocations.py`, and wire
it into the cascade attempt loops in `AIClient.complete`, `AIClient.complete_json`
(non-streaming + streaming-fast-path), and `AIClient.chat`. The recorder is
gated by `ff_ai_invocations_recorder` (default OFF, sunset 2026-09-01) so it
ships dark and is flipped per-environment after smoke. **Writes never raise
into the LLM call path** — recorder failures log `ai_invocations_write_failed`
and are swallowed.

## 3 · Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A: Reuse `ai_platform_spend_daily` with extra columns | No new table | Aggregate row mutated in-place — destroys per-call dimension forever; can't retro-add `outcome` granularity; violates append-only auditability needed for chaos drills | Rejected: shape mismatch |
| B: Push every call to Langfuse only and query Langfuse for analytics | Already wired (`trace_llm` span exists for every provider call) | Vendor lock-in for billable-cost queries; Langfuse retention is 90d on our plan; failure-row enrichment requires Langfuse-side schema updates we don't control; cost-attribution joins to our own tenant table become cross-system | Rejected: ownership |
| C (chosen): New flat `ai_invocations` table, one row per call | Queryable, joinable to `users`/`organizations`, append-only, owned by us, partition-ready later | Write volume during peak generation (~5-10 rows/sec at projected scale); needs partitioning eventually | Chosen — defer partitioning to Stage B (see §4 Negative) |
| D: Partitioned-from-day-one (`partition by range (created_at)`) | Avoids future migration | Partition rotation tooling (`public.ensure_events_outbox_partitions` from M7-A) needs extending; explicit deferral in [IMPLEMENTATION_MILESTONES.md L24](../architecture/IMPLEMENTATION_MILESTONES.md) | Rejected at launch — single table OK to ~50M rows; revisit at Stage B |

## 4 · Consequences

### Positive
- One queryable surface for every chaos-drill question: `SELECT outcome, count(*) FROM ai_invocations WHERE created_at > now() - interval '1h' GROUP BY 1`.
- Per-provider cost attribution unblocked (called out as deferred in m7-pr28
  closure memory). Sum `total_tokens * provider_rate` grouped by `provider`.
- `cascade_position` lets us answer "how often does the cascade reach Anthropic?".
- Failure rows include `error_class` and truncated `error_message` for incident triage.

### Negative / cost
- One Postgres insert per LLM call (~5-10/sec at projected scale, single-digit
  inserts/sec average). Acceptable: insert-only, no update churn; two
  indexes; estimated <50MB/month at current call volume.
- Single-table-without-partitioning will need maintenance once row count
  approaches ~50M (≈18 months at current trajectory). At that point: convert
  to range-partitioned table per Stage B partition tooling, retain 13 months hot.
- Recorder is best-effort — momentary Postgres unavailability means we'll
  miss some rows. **This is by design**: the LLM call must never fail
  because the flight recorder did.

### Neutral / new obligations
- New flag `ff_ai_invocations_recorder` (sunset 2026-09-01).
- Operators MUST flip the flag in prod within 14 days of ship to avoid sunset CI fail.
- Schema CHECK on `outcome IN ('success','failure','breaker_open','cascade_failover')` —
  any new outcome label requires a forward migration.
- Prompt is **hashed**, not stored. The hash is sha256-hex (full 64 chars) so
  it can be joined cross-row. No reversibility — by design.

## 5 · Implementation Plan

- [x] PR(s): `m7-pr30`
- [x] Migration steps: forward-only — `supabase/migrations/20260508020000_ai_invocations.sql` creates the table + RLS + indexes + CHECK constraint. Idempotent (`CREATE TABLE IF NOT EXISTS`, `DROP POLICY IF EXISTS`).
- [x] Feature flag: `ff_ai_invocations_recorder` (default OFF, sunset 2026-09-01)
- [x] Rollback plan: flip flag OFF — recorder becomes a no-op. Migration is additive (no data loss). Table can be dropped if abandoned.
- [x] Observability: new log lines `ai_invocations_write_failed` (recorder swallows), `ai_invocations_recorder_disabled` (DEBUG, sampled).
- [x] Updates to blueprint section §6 (AI runtime).
- [ ] Updates to runbook(s): post-launch — add "query for last hour failure rate" to runbook once flag is ON in prod.

## 6 · Validation

How will we know this decision was correct?

- [ ] Post-launch: a chaos-drill that artificially fails Gemini produces rows with `outcome='cascade_failover'` AND a follow-up row with `outcome='success'` and `provider='anthropic'` for the same logical request.
- [ ] No SLO regression on AI call P50/P99 latency after flag flipped ON in canary (recorder is async + swallows; expected delta < 2ms median).
- [ ] Cost: Postgres write volume for `public.ai_invocations` < 100 inserts/sec sustained.
- [x] Tests: recorder unit tests (success row, failure row, hash determinism, flag-OFF no-op, write-failure swallowed) + cascade-integration test extending the m7-pr28 chaos test.

## 7 · References

- Blueprint section: §6 (AI runtime safety)
- Related ADRs: ADR-0031 (multi-provider — provides `provider` field meaning), ADR-0040 (DLQ — sets the precedent that failures are first-class observable rows, not log-only)
- IMPLEMENTATION_MILESTONES.md M8-B (this PR)
- Streaming paths intentionally out-of-scope for v1 (token counts not finalised until stream completes; revisit when streaming fast-path graduates beyond Gemini-only)
