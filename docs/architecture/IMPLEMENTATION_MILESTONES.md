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

#### M7-D — Bootstrap task registry (`m7-pr27d`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | Introduced `_BOOTSTRAP_TASKS: set[asyncio.Task]` and `_track_bootstrap(coro, *, name)` helper in `backend/app/api/routes/generate/jobs.py`. Replaced the four raw `asyncio.create_task(...)` calls in the `_start_generation_job*` family (Temporal handoff, Redis enqueue, Redis-unavailable fallback, saturation finaliser) with the tracked variant. Extended `backend/main.py` lifespan handler to drain the registry with a 5s bounded `asyncio.wait_for` after draining `_ACTIVE_GENERATION_TASKS`. |
| **Why now** | P0-4: raw `create_task` for fire-and-forget dispatch coroutines was both a weak-reference GC footgun (per Python asyncio docs) and a SIGTERM orphan vector (jobs accepted just before deploy could vanish in the `queued` state with no enqueue). **Closed.** |
| **Risks introduced** | A bootstrap coroutine that exceeds the 5s drain budget is cancelled, but the cancellation is now logged. No new flag — pure-improvement change with no behavioural difference outside SIGTERM windows. |
| **Blast radius** | Generation dispatch path only. Other modules (`JobWatchdog`, `_periodic_stale_job_cleanup`) keep their own task management. |
| **Rollback** | Revert the slice. No data migration involved. |
| **Observability** | New WARN log line `generation_bootstrap_task_failed` (task name + error). Drain telemetry: existing `Draining bootstrap dispatch tasks` / `Bootstrap dispatch tasks drained` / `Bootstrap dispatch drain timed out; cancelling` log lines. |
| **Tests** | `backend/tests/unit/test_bootstrap_task_registry.py` — 5 unit tests covering successful registration, failing coroutine surfacing, cancellation, concurrent registrations, and the lifespan-style bounded drain. Plus regression: `test_queue_ack_on_success.py` (7 tests still green). |
| **Deploy order** | Single PR. No migration. |
| **ADR** | ADR-0041 (Accepted 2026-05-08). |
| **Success criteria** | (✅) All four bootstrap call sites use `_track_bootstrap`. (✅) Lifespan drain wired and bounded. (pending — 30d post-deploy) zero `queued`-with-no-stream-entry incidents observed. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- Generic `app.core.task_registry` module that other modules could adopt — M11.
- Prometheus gauges `bootstrap_tasks_inflight`, `bootstrap_task_failures_total` — M11.
- Mid-flight Temporal-failure-during-cancellation fallback to legacy — deferred until Temporal is at 100% rollout.

#### M7-E — Capability tokens + sandbox tier classifier (`m7-pr29`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | Three new columns on `ai_tools`: `sandbox_tier VARCHAR(2) DEFAULT 'L0'`, `egress_allowlist JSONB DEFAULT '[]'`, `requires_capability_token BOOLEAN DEFAULT FALSE` (migration `20260508010000_ai_tools_sandbox_tier.sql`). Three new modules in `ai_engine/registry/`: `capability.py` (HMAC-signed opaque tokens with `Authorizer.mint`/`verify`, `InProcessNonceStore` LRU + `RedisNonceStore` SETNX replay protection, dual-key rotation), `sandboxes.py` (`L0InProcessSandbox` direct call, `L1HttpxAllowlistSandbox` dispatch-path-only stub that logs `tool_sandbox_l1_unenforced`, `L2GrpcSidecarSandbox` raises with tool name), `resolvers.py` (empty-by-design RESOLVERS allowlist as AP-4 governance hook). `Dispatcher` now accepts `authorizer` + `sandboxes` + `capability_token`; capability check runs after grant check, before input validation; sandbox routing wraps the tool callable. Two new flags `ff_tool_capability_tokens` and `ff_tool_sandbox_tier_routing` (both default OFF, sunset 2026-09-01). |
| **Why now** | P0-5: tools could be invoked with no per-call attestation that the caller was authorised at the moment of execution, and there was no schema-level distinction between trusted in-process tools and tools that should hit the network. Both gaps are now closed at the column + dispatch level — though L1 enforcement is intentionally deferred (see Out-of-scope). |
| **Risks introduced** | None at default (both flags OFF). With flag ON: a misconfigured `tool_capability_secret` rotation could reject every token (mitigated by `previous_secret` overlap key). With routing ON and any L1 tool seeded: the L1 sandbox falls through to L0 — the warning log is the safety net. |
| **Blast radius** | `ai_engine/registry/` only. Generation pipeline does not yet pass `capability_token` (forward-compat: dispatcher accepts the kwarg, callers can wire it in m7-pr29b). |
| **Rollback** | Set both flags OFF; no per-tool rows have `requires_capability_token=true` in seed. Migration is additive (DEFAULT values) so DB rollback unnecessary. |
| **Observability** | New audit error_message values: `capability_authorizer_unset`, `capability_token_missing`, `capability_<reason>` (e.g. `capability_expired`, `capability_nonce_replayed`, `capability_bad_signature`). New log lines: `tool_capability_nonce_inprocess_fallback` (once per process), `tool_capability_nonce_redis_failed`, `tool_sandbox_l1_unenforced` (once per tool), `tool_sandbox_routed`, `tool_sandbox_shadow`. |
| **Tests** | `ai_engine/tests/registry/test_capability.py` — 14 tests (round-trip, expiry, tampering, malformed, mismatches, nonce replay, secret rotation). `test_sandboxes.py` — 8 tests (L0/L1/L2 behaviour, dedup warning, flag-off shadow log, flag-on routing, unknown tier). `test_resolvers.py` — 3 tests (empty-by-design contract). `test_dispatcher.py` extended with 6 capability/sandbox integration tests. **51/51 registry tests green.** Governance: `check_feature_flags.py` and `check_architecture.py` (AP-4) both PASS. |
| **Deploy order** | (1) ship migration, (2) deploy code, (3) flip flags per-environment after smoke. Capability secret seeded via `TOOL_CAPABILITY_SECRET` env. |
| **ADR** | ADR-0032 + ADR-0033 (both Accepted 2026-05-08). |
| **Success criteria** | (✅) Migration applied. (✅) Authorizer mint/verify round-trip green. (✅) Per-tool kill-switch enforced even with global flag OFF. (✅) AP-4 governance still passes. (pending — m7-pr29b) first L1 tool seeded triggers real httpx host-blocking. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- L1 actual httpx host-blocking enforcement — m7-pr29b (triggered by first tool with `sandbox_tier='L1'`).
- L2 gRPC sidecar runtime — M11 (raises `SandboxNotImplemented` for now).
- L3 Firecracker BYO marketplace — separate ADR.
- Wiring `capability_token` through the generation pipeline call sites — m7-pr29b.

**M7 exit gate:** All three success criteria met for ≥7 consecutive days.

---

#### M8-A — Multi-provider AI dispatch (`m7-pr28`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | New `_AnthropicProvider` co-located with `_GeminiProvider` in `ai_engine/client.py` (lazy SDK import, retry-decorated `complete`/`complete_json`/`chat`/`stream_completion`/`complete_json_streaming` with shared `_RETRY_KWARGS`, per-model circuit breaker, Langfuse span, asyncio.Queue producer/consumer for the SDK's blocking `messages.stream`). New `AIClient._select_provider(model_name)` helper dispatches by prefix — `claude-*` → Anthropic, anything else → Gemini default. The cascade loops in `complete()`, `complete_json()` non-streaming path, `stream_completion()`, `chat()` and the streaming-JSON fast-path now route through the helper per candidate model. `model_router._DEFAULT_CASCADE` appends `claude-3-5-sonnet-20241022` as the tier-1 cascade tail for `reasoning`, `fact_checking`, `quality_doc`, `aim_recon`, `aim_writer`, `aim_fix`. New flag `ff_anthropic_provider` (default OFF, sunset 2026-09-01) gates BOTH cascade exposure (resolver strips `claude-*` when OFF) AND dispatch (helper still routes correctly if a caller passes a `claude-*` model directly). New settings: `anthropic_api_key`, `anthropic_default_model`, `anthropic_max_tokens`. `anthropic>=0.40,<1.0` added to `backend/requirements.txt`. |
| **Why now** | P1-4: Gemini is currently the only generation backend. A regional outage or sustained quota exhaustion brings the entire generation pipeline down. Anthropic at the cascade tail closes the single-vendor risk while keeping cost neutral at default (the flag is OFF in ship state). |
| **Risks introduced** | None at default state (flag OFF → resolver strips `claude-*` → no Anthropic call possible even if a route is mis-configured). With flag ON: extra cascade attempts add latency on Gemini-wide failure scenarios (acceptable: failover path is the whole point). Schema is intentionally NOT forwarded to Anthropic — JSON is parsed by the shared `_parse_json` post-processor, identical to the Gemini path. |
| **Blast radius** | `ai_engine/` only. Streaming JSON fast-path remains Gemini-only by design (per ADR-0031): when the primary candidate is Gemini, the streaming path stays on Gemini; if a `claude-*` candidate ever reaches the fast-path it will use the Anthropic streaming bridge (covered by `test_complete_json_streaming_calls_token_sink_per_chunk`). |
| **Rollback** | Set `ff_anthropic_provider=false`. No DB changes. Sunset 2026-09-01. |
| **Observability** | New log line `provider_selected: model=... provider=anthropic` (INFO, once per AIClient on first claude dispatch). New token-sink failure log `token_sink_emit_failed_anthropic`. Per-model circuit breaker key `ai_model_claude-3-5-sonnet-20241022` registered automatically via `_get_model_breaker`. Existing `model_cascade_failover` log + `MetricsCollector.record_model_failover` already cover Gemini→Anthropic transitions. |
| **Tests** | `backend/tests/unit/test_anthropic_provider.py` — 7 tests (round-trip, JSON markdown stripping, JSON-only system instruction, chat passthrough, missing-key raises at lazy-init seam, stream deltas, token sink per chunk). `backend/tests/unit/test_model_routing.py` extended — 3 provider-selection tests (claude/gemini/None dispatch), 2 cascade flag-gating tests (strip when OFF, keep when ON), 1 chaos test (Gemini quota-exhausted on every cascade SKU → Anthropic completes). **25/25 m7-pr28 tests green; 51/51 m7-pr29 registry tests still green.** Governance: `check_feature_flags.py` clean (12 flags), `check_architecture.py` clean. |
| **Deploy order** | (1) deploy code with flag OFF (resolver strips claude entries → no behavioural change). (2) seed `ANTHROPIC_API_KEY` in target env. (3) flip `FF_ANTHROPIC_PROVIDER=true` in canary. (4) chaos-drill verification: artificially fail Gemini, confirm cascade reaches Anthropic. (5) roll to prod. |
| **ADR** | ADR-0031 (Accepted 2026-05-08). |
| **Success criteria** | (✅) Provider helper dispatches by name prefix. (✅) Resolver flag-gating verified by unit test. (✅) Chaos test: full Gemini cascade exhaustion → Anthropic returns successfully. (pending — production canary) Drill against staged "Gemini outage" completes a real generation end-to-end. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- Streaming JSON fast-path reuse for claude-primary routes (today fast-path stays Gemini-only per ADR §6 status-quo).
- Cost telemetry per-provider (waits on `m7-pr30` `ai_invocations` table).
- Tool-use schema forwarding to Anthropic (intentional: cascade contract is "best-effort JSON text").
- Adding Anthropic to non-tier-1 task cascades (`drafting`, `summarization`, etc. remain Flash-only by cost design).

---

### M8 — AI runtime safety

PRs: `m7-pr28` (multi-provider), `m7-pr29` (capability tokens + sandbox), `m7-pr30` (flight recorder), `m7-pr31` (strict event validation).

| PR | Closes | Brief | Depends on |
|---|---|---|---|
| `m7-pr28` ✅ | P1-4 | **SHIPPED 2026-05-08 (M8-A below).** Add Anthropic provider behind `model_router`; cascade Gemini→Anthropic on 5xx/429/circuit-open; chaos test "Gemini quota exhausted" leaves SLO intact. | M7 complete (need DLQ in place before adding new failure modes) |
| `m7-pr29` ✅ | P0-5 | **SHIPPED 2026-05-08 (M7-E above).** Capability tokens minted per-job; tool registry verifies token before exec; classify each tool L0/L1/L2 (per blueprint §6.4). | ADR-0032, ADR-0033 |
| `m7-pr30` ✅ | (foundation) | **SHIPPED 2026-05-08 (M8-B below).** `ai_invocations` table (one row per LLM call): tenant, prompt hash, model, tokens, latency, outcome, retries. Backfill from logs is **not** done (forward-only). | ADR-0034 |
| `m7-pr31` | P1-2 | OutboxWriter rejects events not registered in `packages/events/schema/v1/`. Migrate ~25 currently-unregistered emitters in subsequent PRs over 2 weeks. | ADR-0035 |

**M8 exit gate:** A staged "Gemini full outage" chaos drill completes a generation end-to-end via Anthropic with no SLO violation. All emitted events pass strict schema validation in production for ≥7 days.

#### M8-B — `ai_invocations` flight recorder (`m7-pr30`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | New `public.ai_invocations` table (forward-only, single non-partitioned at launch — see ADR-0034 §4 for partition deferral) writes one row per terminal LLM call (success **or** failure). Migration `supabase/migrations/20260508020000_ai_invocations.sql` creates the table with columns `tenant_id, task_type, model, provider, prompt_hash, prompt_tokens, completion_tokens, total_tokens, latency_ms, outcome, retry_count, cascade_position, flag_anthropic_enabled, error_class, error_message`; CHECK constraints on `outcome IN ('success','failure','breaker_open','cascade_failover')` and `provider IN ('gemini','anthropic','unknown')`; three indexes (`(tenant_id, created_at)`, `(model, created_at)`, partial on non-success); RLS enabled with single SELECT policy gated on `auth.uid()` (no INSERT policy — service role bypasses, deliberately blocks anon/authenticated poisoning). New `ai_engine/observability/ai_invocations.py` module with `AIInvocationsRecorder.record(...)` (best-effort writer; flag-OFF short-circuits; invalid outcome dropped; sha256-hex prompt hash; supabase-unavailable returns `None`; insert exception swallowed). New `_record_invocation` helper on `AIClient` wires the recorder into the cascade attempt loops in `complete()`, `complete_json()` non-streaming cascade, and `chat()` (streaming paths intentionally OUT-OF-SCOPE per ADR §7). Per-attempt `time.monotonic()` start; success branch records `outcome='success'` with `cascade_position=i`; CircuitBreakerOpen branch records `outcome='breaker_open'`; Exception branch records `outcome='cascade_failover'` if a next candidate exists else `outcome='failure'`. New flag `ff_ai_invocations_recorder` (default OFF, sunset 2026-09-01). |
| **Why now** | After `m7-pr28` added Anthropic as cascade tail, no persistent record existed for failure cases (5xx, quota exhaustion, circuit-breaker open, JSON-validation failure). The existing `_track_usage` log line is forward-only stream and emitted only on success. Without one row per LLM call we cannot answer the chaos-drill verification questions: "how often does the cascade reach Anthropic?", "what fraction of `aim_recon` calls produce `cascade_failover`?". This PR closes that observability gap and unblocks per-provider cost telemetry deferred from m7-pr28. |
| **Risks introduced** | None at default state (flag OFF → recorder is a no-op). With flag ON: one Postgres insert per LLM call adds <2ms median latency (recorder is async; insert failure is swallowed). Single-table-without-partitioning will need conversion at ~50M rows (deferred to Stage B). |
| **Blast radius** | `ai_engine/client.py` cascade loops + new `ai_engine/observability/ai_invocations.py` + new migration. Streaming paths (`stream_completion`, `complete_json` streaming-fast-path) intentionally untouched per ADR §7 — token counts are not finalised mid-stream. |
| **Rollback** | Set `ff_ai_invocations_recorder=false`. No data loss (additive migration). Table can be dropped if abandoned. |
| **Observability** | New log lines: `ai_invocations_write_failed` (recorder swallows DB errors), `ai_invocations_supabase_unavailable` (DEBUG, lazy-init failure), `ai_invocations_invalid_outcome` (defensive). New queryable surface: `SELECT outcome, count(*) FROM ai_invocations WHERE created_at > now() - interval '1h' GROUP BY 1`. Failure rows include `error_class` (qualified type) and truncated `error_message` (≤500 chars). |
| **Tests** | `backend/tests/unit/test_ai_invocations_recorder.py` — 9 tests (flag-OFF no-op, success row fields, failure row truncation, sha256 determinism, invalid outcome dropped, supabase-unavailable swallow, insert-exception swallow, provider inference for all 5 model families, singleton behaviour). **34/34 m7-pr28+m7-pr30 tests green.** Governance: `check_feature_flags.py` clean (13 flags), `check_architecture.py` clean (no `ai_engine → backend.*` imports). |
| **Deploy order** | (1) apply migration. (2) deploy code with flag OFF (recorder is no-op). (3) flip `FF_AI_INVOCATIONS_RECORDER=true` in canary. (4) run query `SELECT outcome, count(*) FROM ai_invocations` to confirm rows are arriving. (5) roll to prod. (6) flag MUST be flipped within 14 days to avoid sunset CI fail. |
| **ADR** | ADR-0034 (Accepted 2026-05-08). |
| **Success criteria** | (✅) Migration applied. (✅) Recorder writes both success and failure rows. (✅) Prompt body never persisted (sha256-hex only). (✅) Recorder failures never propagate. (pending — production canary) chaos-drill that fails Gemini produces `cascade_failover` rows followed by `success`+`provider=anthropic` for the same logical request. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- Recorder wiring into `stream_completion()` and `complete_json()` streaming-fast-path — revisit when streaming graduates beyond Gemini-only (token counts not finalised mid-stream per ADR §7).
- Range-partitioning of `ai_invocations` — deferred to Stage B trigger (~50M rows).
- Per-provider cost dashboards joining `ai_invocations.total_tokens` to provider rate cards — follow-up PR after flag is ON in prod for ≥7 days.
- Tenant-level cost rollups (joining `tenant_id` to `organizations`) — belongs in analytics layer, not this PR.

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
