# Implementation Milestones

**Status:** Canonical · Sequenced execution plan
**Companion to:** [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md) §18, §22

> The blueprint says **what** the architecture must become.
> This file says **in what order, and how each step lands safely**.
>
> Milestones are sequential. Do not start milestone N+1 until N's success criteria are met.
> Skipping a milestone requires architecture-WG sign-off and an ADR documenting the skip.

---

## Stage A milestones (today → 50K generations/day)

### M7 — Reliability foundation **(NEXT)**

PRs: `m7-pr27` (split into 27a, 27b, 27c if ≥500 lines each).

#### M7-A — Partition rotation (`m7-pr27a`) ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | Installed `pg_cron` extension. Added `public.ensure_events_outbox_partitions(p_months_ahead int)` PL/pgSQL function (idempotent, preserves existing `events_outbox_YYYY_MM` naming). Scheduled daily 00:01 UTC via `cron.schedule('events-outbox-rotation', ...)`. Bootstrap call in the migration ensures 4 months exist immediately. Added `partition_rotation_audit` table (RLS, service-role only) for run telemetry. **Scope intentionally limited to `events_outbox`** — `agent_events` and `ai_invocations` are not yet partitioned (deferred to M7-D / Stage-A trailing). |
| **Why this design (vs. blueprint pg_partman)** | Existing partition naming (`events_outbox_YYYY_MM`) is incompatible with pg_partman's default (`events_outbox_pYYYYMMDD`). Adopting would require renaming live partitions (lock + risk + violates expand-only). pg_cron + 100-line function is more auditable for Stage A. Stage-B re-evaluation trigger documented in ADR-0037. |
| **Why now** | P0-1: only 3 monthly partitions seeded today; INSERTs would fail at 2026-08-01 00:00 UTC. **Closed on this migration** via bootstrap call. |
| **Risks introduced** | (a) `pg_cron` extension is now active in production — additional auditable surface. (b) `cron.schedule` job runs as `postgres` superuser; mitigated by `REVOKE ALL` + scoped `GRANT EXECUTE` on the function. (c) If cron stops silently and operator misses the alert window, partitions could lag — mitigated by the 4-month headroom (any single missed day still leaves 3 months of runway). |
| **Blast radius** | Bootstrap call: ~50ms (4 `CREATE TABLE IF NOT EXISTS PARTITION OF` statements). No table rewrites. Daily cron: identical, runs in seconds. |
| **Rollback** | (a) `SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = 'events-outbox-rotation';` (b) Function remains for manual invocation. (c) Drop pg_cron last, only after a replacement is in place. Break-glass procedure documented in `docs/runbooks/outbox-partitions.md` §4. |
| **Observability** | `partition_rotation_audit.ran_at` row appended on each invocation. Alert (M7-D wiring): `partition_rotation_audit_last_ran_at_age > 36h`. Manual query: `SELECT MAX(ran_at) FROM public.partition_rotation_audit WHERE table_name = 'events_outbox';` |
| **Tests** | `backend/tests/integration/test_outbox_partitions.py` — 8 static contract tests (always run) + 4 live-DB tests (opt-in via `INTEGRATION_DB_URL`). Static tests lock pg_cron install, function signature, SECURITY DEFINER, search_path pin, REVOKE/GRANT, bootstrap call, daily schedule, and SAFETY header. Live tests verify function callability, presence of next-4-month partitions, audit row recording, cron job active state. |
| **Deploy order** | Single migration: `supabase/migrations/20260508120000_outbox_partition_rotation.sql`. Idempotent. Apply during any maintenance window or live (no locks). Verify with `pytest backend/tests/integration/test_outbox_partitions.py` (live profile) post-deploy. |
| **ADR** | ADR-0037 (Accepted 2026-05-08). |
| **Success criteria** | (✅ migration-time) Zero partition-related INSERT errors. (pending — 30d post-deploy) `partition_rotation_audit` shows daily rows with no error_message. Manual chaos drill: `SELECT cron.unschedule(...)` then 36h later confirm alert fires (deferred to M7-D). |
| **Owner DRI** | @BalaShankar9 |

#### M7-B — Eliminate in-process fallback (`m7-pr27b`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changes** | Collapse the three-tier dispatch ladder to two tiers in production. Tier-3 (in-process) is gated behind `ff_inprocess_fallback` (default OFF) and **bounded** by `inprocess_max_concurrent` (default 4). When the flag is OFF and Redis is unavailable, the job is finalised as `failed` with a retryable message — durable, observable, and immediate. When the flag is ON (dev / single-process deploys) over-cap requests fail fast instead of queueing forever. |
| **Why this design (vs. blueprint "delete tier-3 entirely")** | The in-process path is still the only viable execution surface for `make dev` / single-process deploys where there is no Redis worker process. We keep the path, gate it, bound it, and **sunset it on 2026-08-31** (enforced by `check_feature_flags.py`). Full justification in ADR-0038 §"Considered alternatives". |
| **Why now** | P0-2: unbounded `asyncio.create_task` in web pod = OOM under sustained queue outage; silently loses jobs on pod restart. Real survivability beats fake availability. **Closed.** |
| **Risks introduced** | A simultaneous Temporal + Redis outage now finalises generation jobs as failed with a retryable message (was: silent acceptance). Customers see real failure during a real outage — by design. |
| **Blast radius** | Generation endpoint only, only when *both* Temporal and Redis are down. |
| **Rollback** | Set `ff_inprocess_fallback=true` to re-enable the dev path; the fallback is still bounded. Sunset 2026-08-31. |
| **Observability** | Existing log lines: `generation_dispatch_failed_redis_unavailable` (flag-off path), `generation_inprocess_saturated` (over-cap), `generation_job_inprocess_fallback` (flag-on accept). Prometheus counter `generation_dispatch_fallback_total{tier=...}` deferred to M11 observability uplift (recorded as out-of-scope in ADR-0038). |
| **Tests** | `backend/tests/unit/test_inprocess_fallback_gate.py` — 4 unit tests covering flag-off-Redis-down, flag-on-Redis-down, saturated semaphore, under-cap. |
| **Deploy order** | Single PR. New defaults are production-safe (flag off). Set `FF_INPROCESS_FALLBACK=true` only on dev / single-process environments before merging. |
| **ADR** | ADR-0038 (Accepted 2026-05-08). |
| **Success criteria** | (✅) `_start_generation_job_inprocess` is unreachable in production absent the flag. (✅) Capacity cap enforced via test. (pending — 14d post-deploy) zero `generation_inprocess_saturated` events from prod (web pods). |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- Wiring `_try_temporal()` and `_try_enqueue()` bootstrap coroutines into a managed task registry for graceful shutdown. Tracked as `m7-pr27d` (orphan task hygiene).
- Prometheus counter `generation_dispatch_fallback_total{tier=...}` — M11.

#### M7-C — ACK-on-success queue semantics + DLQ (`m7-pr27c`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | Refactored `backend/app/core/queue.py::_dispatch` to ACK only after handler returns success, gated behind `ff_queue_ack_on_success` (default OFF, sunset 2026-09-01). Flag-on path: read delivery count via `XPENDING`, DLQ to `events:dlq` after `queue_max_deliveries` (default 5), insert into new `processed_queue_events` table on success for consumer-side idempotency. Flag-off path is bit-for-bit identical to pre-ADR-0040 behaviour. |
| **Why this design (vs. blueprint "delete legacy path")** | The events bus (`backend/app/core/events/consumer.py`) already implements this exact pattern — we mirror it verbatim rather than invent a second protocol. The flag exists so each environment can flip and observe `events:dlq` + `processed_queue_events` row count before legacy is deleted at sunset. |
| **Why now** | P0-3: current always-ACK-in-finally swallows handler exceptions; failures only surface if the handler's defensive DB write itself succeeds. **Closed.** |
| **Risks introduced** | (a) A pathologically slow handler (>5 min) could be reclaimed and run twice before completing once; the second run's dedup row is missing because the first hasn't returned yet. Job-state guards in `_run_generation_job_via_runtime` prevent duplicate user-visible side-effects (worst case: wasted compute). (b) DLQ depth becomes a new monitoring surface (matches events bus). |
| **Blast radius** | Generation queue consumer only. A poison message stalls only its own msg_id slot; sibling reads continue. |
| **Rollback** | Set `FF_QUEUE_ACK_ON_SUCCESS=false`. Legacy behaviour returns immediately. |
| **Observability** | Existing log lines: `queue.dead_lettering`, `queue.duplicate_delivery_skipped`, `queue.job_handler_error` (now WARN with `delivery` field). DLQ inspection via `XRANGE events:dlq`. Prometheus counters `queue_ack_total{outcome,consumer}`, `queue_dlq_total{consumer}`, `queue_pending_redeliveries{consumer}` deferred to M11. |
| **Tests** | `backend/tests/unit/test_queue_ack_on_success.py` — 7 unit tests covering legacy contract, success path, retry path, DLQ at-max, DLQ over-max, duplicate-dedup tolerance, malformed message. |
| **Deploy order** | Migration (`20260508_processed_queue_events.sql`) + code in same PR. Flip flag per-environment after smoke drill (synthetic 5-attempt poison message → DLQ appears). |
| **ADR** | ADR-0040 (Accepted 2026-05-08). |
| **Success criteria** | (✅) Flag-off behaviour preserved (test). (✅) Flag-on retries on transient handler error (test). (✅) DLQ on max-attempts (test). (pending — 30d post flag-flip) zero observed silent event loss. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- DLQ replay tool / runbook — M11.
- Prometheus counters for queue ACK / DLQ / redeliveries — M11.
- Pruning sweeper for `processed_queue_events` (and sibling `consumed_events`) — M7-D.
- Per-event-type DLQ stream routing (currently single shared `events:dlq` with `consumer` discriminator).

**M7 dependencies:** none. M7-A, B, C may ship in parallel branches but **must merge in order A→B→C** because B's 503 logic relies on C's metrics for canary decisioning.

**M7 exit gate:** All three success criteria met for ≥7 consecutive days.

---

### M8 — AI runtime safety

PRs: `m7-pr28` (multi-provider), `m7-pr29` (capability tokens + sandbox), `m7-pr30` (flight recorder), `m7-pr31` (strict event validation).

| PR | Closes | Brief | Depends on |
|---|---|---|---|
| `m7-pr28` | P1-4 | Add Anthropic provider behind `model_router`; cascade Gemini→Anthropic on 5xx/429/circuit-open; chaos test "Gemini quota exhausted" leaves SLO intact. | M7 complete (need DLQ in place before adding new failure modes) |
| `m7-pr29` | P0-5 | Capability tokens minted per-job; tool registry verifies token before exec; classify each tool L0/L1/L2 (per blueprint §6.4). | ADR-0032, ADR-0033 |
| `m7-pr30` | (foundation) | `ai_invocations` table (one row per LLM call): tenant, prompt hash, model, tokens, cost, latency, outcome, retries. Backfill from logs is **not** done (forward-only). | ADR-0034 |
| `m7-pr31` | P1-2 | OutboxWriter rejects events not registered in `packages/events/schema/v1/`. Migrate ~25 currently-unregistered emitters in subsequent PRs over 2 weeks. | ADR-0035 |

**M8 exit gate:** A staged "Gemini full outage" chaos drill completes a generation end-to-end via Anthropic with no SLO violation. All emitted events pass strict schema validation in production for ≥7 days.

---

### M9 — Workflow durability

PR: `m8-pr32` — per-stage Temporal activities.

| Field | Value |
|---|---|
| **What changes** | Convert PR-24 outer-only envelope into per-stage activities (intake → research → draft-resume → critique → variant-lab → score → finalize). Each stage is its own activity with idempotency key + retry policy. Mid-pipeline crash resumes from last completed activity. |
| **Why now** | P1-1: today a worker crash mid-pipeline re-burns tokens for completed stages. |
| **Risks** | Activity proliferation increases Temporal history size. Mitigated by checkpoint-only outputs (not full intermediate state). |
| **Blast radius** | Generation engine only. Existing PR-24 envelope kept under `ff_temporal_per_stage` until new path proven. |
| **Rollback** | Flag `ff_temporal_per_stage=false` reverts to envelope-only path. Sunset 2026-12-01. |
| **Observability** | Per-stage activity duration, retry count, idempotency-hit rate. |
| **Tests** | Resume-after-crash integration test in `tests/temporal/test_resume.py`. |
| **ADR** | ADR-0036. |
| **Success criteria** | Worker pod kill mid-pipeline → next worker resumes without re-running completed stages → user-visible cost unchanged. Verified via load + chaos test. |

---

### M10 — Repo health & enforcement maturity

PRs: `m9-pr33` through `m9-pr36`.

| PR | Closes | Brief |
|---|---|---|
| `m9-pr33` | P1-5 | Single migration root. Migrate `database/migrations/*.sql` content into `supabase/migrations/`; delete `database/`. Update `test_supabase_migrations_mirror`. |
| `m9-pr34` | P1-6 | Single `main.py`. Pick `backend/app/main.py` as canonical; redirect `backend/main.py` to it as a shim that emits a deprecation warning on import; remove shim 30 days later. |
| `m9-pr35` | P1-7 | Real codegen for events package: Python via `datamodel-code-generator`; TS via `json-schema-to-typescript`; Kotlin via `quicktype`. CI fails if generated artifacts drift from schema. |
| `m9-pr36` | P1-14 | Wire `import-linter` as required CI check (initially `continue-on-error: true` for 1 week to baseline; then required). |

**M10 exit gate:** Zero migration drift. Single `main.py` import path. Generated event clients in use by at least one consumer per language.

---

## Stage A trailing items (M11+, no PR numbers yet)

| Item | Closes | Trigger to start |
|---|---|---|
| `mypy --strict` on `ai_engine/` | TD-1 | After M8 closed |
| Coverage gate at 70% on `ai_engine/` | TD-2 | After M8 closed |
| `prometheus_client` migration for `/metrics` | TD-3 | After M8 closed |
| Sentry redaction depth → 16 | TD-4 | Anytime; safe |
| Feature flag sunset enforcement (CI fail past sunset) | (governance) | After `config/feature_flags.yaml` exists with ≥5 flags |
| Staging mirror of prod data shape | P1-15 | After M10 |

---

## Stage B trigger triage milestones (placeholders)

Activated only when [`SCALING_PHASES.md`](./SCALING_PHASES.md) Stage-B triggers fire.

- **MS-B1** Cell protocol activation (ADR-0030) — at first enterprise customer requiring isolation.
- **MS-B2** Realtime gateway extraction — at sustained 5K concurrent SSE streams.
- **MS-B3** Kafka introduction — at first analytics consumer requiring 30-day replay.
- **MS-B4** WorkOS SSO/SCIM — at first paid Enterprise tier.
- **MS-B5** SOC 2 Type II evidence — concurrent with MS-B4.

Detailed plans for each will be authored at trigger time, not now (per anti-overengineering checklist).

---

## Tracking

- Each milestone gets a GitHub Project board column.
- Each PR in a milestone has the milestone tag.
- Weekly architecture-WG meeting reviews: open milestone, blockers, next milestone unblock criteria.
- Monthly: prune any milestone whose triggers no longer apply.
