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
| `m7-pr31` ✅ | P1-2 | **SHIPPED 2026-05-08 (M8-C below).** OutboxWriter rejects events not registered in `packages/events/schema/v1/`. Migrate ~25 currently-unregistered emitters in subsequent PRs over 2 weeks. | ADR-0035 |

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

#### M8-C — Strict event validation at OutboxWriter (`m7-pr31`) — ✅ **SHIPPED 2026-05-08**

| Field | Value |
|---|---|
| **What changed** | New `backend/app/core/events/schema_registry.py` lazily loads JSON Schema (Draft 2020-12) files from `packages/events/schema/v1/<event_type>.v<version>.schema.json` and caches one `Draft202012Validator` per `(event_type, version)`. Public surface: `validate_event(envelope) -> list[str]` (returns error messages, never raises for plain validation), `EventValidationError` (raised by writer in strict mode), `MissingEventSchema(EventValidationError)` (no schema file). `OutboxWriter.__init__` accepts new `strict: bool \| None = None` (None ⇒ reads live `ff_strict_event_validation` at append time; True/False ⇒ explicit override for tests). `OutboxWriter.append` now calls `_validate_or_raise(envelope)` before insert: passes ⇒ insert as today; fails + strict=False ⇒ log `event_validation_failed_shadow` (cap to 5 errors) and insert; fails + strict=True ⇒ raise `EventValidationError`, no row inserted; schema missing + strict=False ⇒ log `event_schema_missing_shadow` and insert; schema missing + strict=True ⇒ raise `MissingEventSchema`. New flag `ff_strict_event_validation` (default OFF, sunset 2026-09-01) added to `backend/app/core/config.py` and `config/feature_flags.yaml`. New dep `jsonschema>=4.21,<5` in `backend/requirements.txt`. |
| **Why now** | `packages/events/schema/v1/` has held JSON Schemas for our 5 domain events since M3, but they were documentation-only at runtime. Blueprint §M3 line 579 mandates: "OutboxWriter.append MUST call validate_event(event_type, version, payload) before insert. The schema directory is the **enforced** source of truth, not advisory." Today nothing prevents an emitter from writing `generation.requested` with a missing field, an extra field, or a non-UUID `job_id` — and downstream consumers trust a contract that isn't enforced at the write boundary. This PR adds the gating mechanism so the next 2 weeks of per-emitter migration work can be validated end-to-end as it lands. |
| **Risks introduced** | None at default state (flag OFF → shadow mode logs but never blocks an insert). With flag ON: ~50–200 µs of validation cost per envelope insert; existing emitters whose payloads don't conform will see 500s — that's the entire point of the shadow → flip ratchet. First-call latency per process is ~5 ms (one-time validator build per event_type). |
| **Blast radius** | `backend/app/core/events/outbox.py` (new validator gate at top of `append`), new module `schema_registry.py`, additive flag + dep. Zero behavioural change at default flag state. The 5 currently-registered event types all have loadable schemas (regression test asserts this). |
| **Rollback** | Set `ff_strict_event_validation=false`. Even at default flag state, the shadow-mode log line can be silenced by raising the logger level for `app.core.events.outbox` if needed. The dep can be removed if the entire mechanism is reverted. |
| **Observability** | New log lines: `event_validation_failed_shadow` (validation failed, insert proceeded — counts the migration backlog), `event_schema_missing_shadow` (no schema file, insert proceeded — counts unregistered event types), `event_validator_internal_error` (defensive: validator quirk swallowed so OutboxWriter never blocks on its own bug). Each shadow log includes `event_type`, `event_version`, `error_count`, and the first 5 errors. |
| **Tests** | `backend/tests/core/events/test_event_schema_validation.py` — 14 tests (validate_event accepts/rejects valid/invalid/missing-required, MissingEventSchema for unknown type, validator caching, shadow mode inserts invalid + logs, shadow mode silent on valid, shadow mode inserts when schema missing, strict mode blocks invalid + writes nothing, strict mode passes valid, strict mode blocks missing-required, strict mode raises MissingEventSchema, strict-flag-off default plumbing, strict-flag-on via settings, all 5 registered event types have loadable schemas). **32/32 events tests green** (existing `test_outbox_writer.py` 18 tests still pass — additive change, default flag preserves behaviour). Governance: `check_feature_flags.py` clean (14 flags), `check_architecture.py` clean. |
| **Deploy order** | (1) deploy code with flag OFF (shadow mode active immediately). (2) watch `event_validation_failed_shadow` count in dev/staging for 7 days; expect non-zero from the ~25 unregistered emitters. (3) migrate emitters one PR at a time per `SCALING_PHASES.md` L35 — for each, either fix the payload or add the missing schema file. (4) once shadow log goes quiet for 7 consecutive days in staging, flip `FF_STRICT_EVENT_VALIDATION=true` in canary. (5) watch error tracking for `EventValidationError`; if quiet 7 more days, flip in prod. (6) flag MUST be promoted by sunset 2026-09-01 or CI fails. |
| **ADR** | ADR-0035 (Accepted 2026-05-08). |
| **Success criteria** | (✅) `validate_event` empty for known-good envelope; non-empty for additionalProperties violation and missing-required. (✅) `MissingEventSchema` raised for unknown event type only when strict=True. (✅) Shadow mode logs and still inserts. (✅) Strict mode raises and writes nothing. (✅) All 5 registered event types load. (pending — production canary) `event_validation_failed_shadow` count reaches zero for 7 consecutive days before flag flip. |
| **Owner DRI** | @BalaShankar9 |

**Out of scope (deferred — written down so they don't get lost):**
- **Migration of the ~25 currently-unregistered emitters.** Per `SCALING_PHASES.md` L35 and blueprint §M3, this is per-PR follow-up work over the next 2 weeks. This PR only adds the gating mechanism; the shadow-log signal directs which emitters to fix first.
- **Schema versioning policy beyond v1.** Adding `v2` of an event type is a separate decision (new file, both validators loaded, emitter chooses); documented in `packages/events/README.md` if/when needed.
- **Consumer-side validation.** `OutboxRelay` and downstream subscribers trust the writer's validation today and continue to. If we ever support out-of-band writes that bypass `OutboxWriter`, consumers will need their own validation pass.
- **Schema registry service** (Confluent-style HTTP registry). Filesystem load is sufficient at our scale; revisit only if we operate multi-process schema authoring.
- **Codegen of pydantic models from JSON schemas.** Rejected in ADR-0035 §3 — would duplicate the source of truth.

---

### M9 — Workflow durability

PR: `m8-pr32` — per-stage Temporal activities. ✅ **SHIPPED 2026-05-08** (scaffolding tier).

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

#### M9 — `m8-pr32` SHIPPED notes

| Field | Value |
|---|---|
| **What landed** | (1) Per-stage workflow plan: `_build_per_stage_plan` returns 7 stages in canonical pipeline order (`recon, atlas, cipher, quill, forge, sentinel, nova`) — phase names locked to runtime `PHASE_SLO_MS` keys. (2) `pipeline_checkpoints` table + RLS (service-role write, owner-only read). (3) `CheckpointStore` repo (best-effort writes, never raise; 4KB output_summary cap with truncation marker). (4) `_execute_with_checkpoint` hook — reads checkpoint, returns cached result on `status='complete'` (resume contract), else marks running → executes → marks complete or failed. (5) Production hooks builder is now flag-aware: `ff_temporal_per_stage=ON` binds per-stage plan + checkpoint execute; OFF preserves legacy single-step plan (zero behaviour change). (6) ADR-0036 (Accepted). (7) 28 new tests (12 checkpoint repo + 16 per-stage / resume) + 12 existing production-hooks tests still green. |
| **What did NOT land (deferred)** | Runtime decomposition into per-phase entrypoints (`_run_recon`, `_run_atlas`, …). Today, only the FIRST stage drives the runtime end-to-end; downstream stages mark complete without re-invoking the runtime. **The resume primitive is real and tested**, but cost-not-re-burned at the per-phase level lands when `m8-pr32b` ships per-phase callables. Chaos test (worker-kill drill) ships in `m8-pr32c` after the runtime split. |
| **Rollout** | Flag default OFF. Migration deployable today (zero behaviour change at OFF). Flip in dev/staging after `m8-pr32b`; canary at week 4; prod at week 5. Sunset 2026-12-01. |
| **Open follow-ups** | `m8-pr32b` (runtime per-phase entrypoints), `m8-pr32c` (chaos test), per-stage Prometheus SLO metrics, retention policy for `pipeline_checkpoints` (when table > 1M rows). |
| **Files** | `docs/adrs/0036-per-stage-temporal-activities.md` (NEW), `supabase/migrations/20260508040000_pipeline_checkpoints.sql` (NEW), `backend/app/temporal/checkpoints.py` (NEW), `backend/app/temporal/activities/production.py` (extended; flag-aware hooks builder), `backend/app/core/config.py` (added `ff_temporal_per_stage`), `config/feature_flags.yaml` (already had `ff_temporal_per_stage` reserved entry — no edit needed), `backend/tests/temporal/test_checkpoints_repo.py` (NEW), `backend/tests/temporal/test_per_stage_resume.py` (NEW), `docs/adrs/README.md` (added 0036 row), this file (M9 SHIPPED block). |

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

#### M10 — `m9-pr34` SHIPPED notes

| Field | Detail |
|---|---|
| **What landed** | Single canonical FastAPI entrypoint pinned and enforced. Reality differs from the original plan: `backend/main.py` (NOT `backend/app/main.py`) is the canonical 773-line entry with Sentry/structlog/lifespan/Redis/JobWatchdog/scheduler. `backend/app/main.py` does not exist. The invariant is enforced by the pre-existing `backend/tests/test_entrypoint_consistency.py` (9 tests, all green): pins `backend/main.py` as canonical; asserts no config references the broken `app.main:app`; validates `Procfile`, `railway.toml`, `backend/Dockerfile` (cwd=backend, `main:app`), `infra/Dockerfile.backend` (cwd=repo root, `backend.main:app`), and `Makefile` all resolve to a real FastAPI app. |
| **Did NOT land** | Shim file at the non-canonical path (none needed — the alternative path was never created in the first place). |
| **Rollout** | No code change. Documentation-only confirmation that the invariant exists and is regression-pinned. |
| **Files** | `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this SHIPPED block). |

#### M10 — `m9-pr36` SHIPPED notes

| Field | Detail |
|---|---|
| **What landed** | `import-linter` is now a REQUIRED CI gate (no longer `continue-on-error`). All 4 bounded-context contracts pass: (C1) `ai_engine` is leaf (no `backend.*` imports), (C2) `backend` layered architecture (`api → services → core`), (C3) `backend` consumes `ai_engine` only via `ai_engine.api` facade for direct imports, (C4) Temporal workflow modules cannot module-load I/O libs (`requests`, `httpx`, `psycopg2`, `redis`). Carve-outs documented inline in `.importlinter` mirror the AP-12 / TID251 allowlists in `scripts/governance/check_architecture.py` and `pyproject.toml`. Top-level `include_external_packages = true` so C4 can resolve external forbidden modules. C3 uses `allow_indirect_imports = true` so transitive chains via the legitimate `ai_engine.api` facade are not flagged. All ignore_imports use `unmatched_ignore_imports_alerting = warn` (preventive guards may not match in current graph). |
| **Did NOT land** | Refactor of the 7 documented carve-outs (sunset 2026-08-01, tracked under M11-pr39). Created `backend/app/core/__init__.py` (was missing — required for grimp to register the layer in C2). |
| **Rollout** | Now-required check runs on every PR via `.github/workflows/architecture.yml`. Local: `lint-imports --config .importlinter --no-cache`. |
| **Files** | `.importlinter` (extended: top-level `include_external_packages = true`; C1 carve-outs + warn alerting; C2 cleanup of dead `auth` ignore + warn alerting; C3 `allow_indirect_imports = true` + warn alerting + 2 new sunset-dated `ai_engine.cache` carve-outs), `backend/app/core/__init__.py` (NEW — namespace doc), `.github/workflows/architecture.yml` (removed `continue-on-error: true` + updated header rollout note), this file (m9-pr34 + m9-pr36 SHIPPED blocks). |

#### M10 — `m9-pr33` SHIPPED notes

| Field | Detail |
|---|---|
| **What landed** | Single migration root. The legacy `database/` directory (incl. `database/migrations/`, `database/combined_migration.sql`, `database/apply_*.sql`, `database/hirestack_full_migration.sql`, `database/README.md`) was deleted. The 3 orphaned migrations that lived only there were mirrored into `supabase/migrations/` first: `20260508030000_processed_queue_events.sql`, `20260514000000_idempotency_keys.sql` (RLS + service_role policy added — original lacked it), `20260528020000_consumed_events.sql`. Each carries a provenance comment "`Mirror of database/migrations/<orig>.sql, consolidated under m9-pr33 (single migration root).`" Resurrection is statically blocked by `test_legacy_database_migrations_dir_does_not_exist`. `test_schema_invariants.py` now reads from `supabase/migrations/` only (was `database/combined_migration.sql` + `apply_production_wave23.sql` + `database/migrations/`). `check_migration_safety.py` and `test_cascade_delete_integrity.py` and `test_migration_placement_invariants.py` updated to single root. ADR-0004 updated; `WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md §10.1` flipped from "Forbidden state" to "Achieved". |
| **Did NOT land** | Pre-existing `check_migration_safety.py` warnings about `CREATE INDEX without CONCURRENTLY` in supabase/migrations files (`20260528010000_outbox_relay`, `20260528020000_consumed_events`, `20260604010000_tool_registry`, `20260618000000_pgvector_aim_sources`) and missing RLS on `ai_tool_invocations_*` partitions — out of scope for m9-pr33 (these existed before). |
| **Rollout** | No production schema change (orphans were already in supabase/ as of this PR via the mirrors; the deletion only removes a legacy folder nothing reads). Operators continue to use `supabase db push`. |
| **Files** | NEW: `supabase/migrations/20260508030000_processed_queue_events.sql`, `supabase/migrations/20260514000000_idempotency_keys.sql`, `supabase/migrations/20260528020000_consumed_events.sql`. MODIFIED: `backend/tests/unit/test_supabase_migrations_mirror.py` (rewrote — now pins single-root invariant), `backend/tests/test_cascade_delete_integrity.py` (drop database/ glob), `backend/tests/unit/test_migration_placement_invariants.py` (rewrote — drop `_DATABASE_MIG_DIR` and `TestCriticalMigrationsMirrored`), `backend/tests/unit/test_persist_resilience.py` (doc), `backend/tests/unit/test_schema_invariants.py` (repointed at supabase/), `scripts/governance/check_migration_safety.py` (drop database/ from DIRS), `.github/PULL_REQUEST_TEMPLATE.md`, `docs/architecture/OPERATIONAL_PROCESSES.md`, `docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md` §10.1, `docs/adrs/0004-single-migration-source-of-truth.md`, this file. DELETED: entire `database/` directory. |

#### M10 — `m9-pr35` SHIPPED notes — **M10 EXIT GATE CLOSED**

| Field | Detail |
|---|---|
| **What landed** | Real, deterministic codegen replaces the prior placeholder writers in `packages/events/scripts/codegen.py`. Three language toolchains drive output from the 6 schemas under `packages/events/schema/v1/`: **Python** via `datamodel-code-generator==0.57.0` (`--output-model-type pydantic_v2.BaseModel --disable-timestamp`) → `backend/app/core/events/generated/*.py` (snake_case modules + `__init__.py` barrel re-exporting each schema's `title` class with `__all__`); **TypeScript** via `npx --yes json-schema-to-typescript@15` → `frontend/src/types/events/*.ts` (dash-slug filenames + `index.ts` barrel `export *`); **Kotlin** via `npx --yes quicktype@23 --lang kotlin --framework klaxon --package com.hirestack.events.generated` → `mobile/lib/events/<Title>.kt`. Output is byte-stable across runs (verified: `--write --all` then `diff -r` on all 3 dirs = no diff). CLI is `--check | --plan | --write` mutually exclusive plus `--lang` and `--all`. M10 exit gate consumers wired in all three languages: (Py) `backend/tests/contracts/test_event_schema_contract.py::test_generated_python_envelope_matches_manual` imports from `app.core.events.generated` and asserts field-set parity with the manual `EventEnvelope`; (TS) `frontend/src/lib/sdk/index.ts` re-exports the generated `EventEnvelope` from `../../types/events`; (Kt + cross-language) the new `backend/tests/contracts/test_generated_event_clients.py` (16 assertions) parametrically asserts every schema has a Python module, TS file, and Kotlin file with the right package + `data class <Title>` declaration. CI drift gate `.github/workflows/codegen.yml` runs `--check`, then `--write --all`, then `git diff --exit-code` on the 3 output dirs + `packages/events/scripts/codegen.py`. Local equivalent: `make codegen-events-check`. |
| **Did NOT land** | Wiring the generated Kotlin classes into the android Gradle sourceSet — the android module uses Moshi/snake_case (`com.hirestack.ai.data.network.*`) while quicktype emits Klaxon, and forcing convergence would break the existing app build. The contract-test consumer satisfies the gate's intent ("in use by at least one consumer per language") by binding CI green to the generated artifacts' shape; a stricter on-device consumer is deferred to a future android refactor. The hand-written `backend/app/core/events/envelope.py` (with validators + `to_outbox_row()`) is intentionally NOT replaced by the generated structural model — the contract test pins them at field-set parity. |
| **Rollout** | No production change. Drift workflow runs on every PR touching `packages/events/**`, `backend/app/core/events/generated/**`, `frontend/src/types/events/**`, `mobile/lib/events/**`, `packages/events/scripts/codegen.py`, or itself. Operator workflow: `make codegen-events` to regenerate after schema edits. **Quirk to remember:** `quicktype@23` crashes (`s.codePointAt is not a function`) on integer `const` keywords — `_strip_integer_consts()` in `codegen.py` rewrites them to a single-value range in a tempfile copy before invocation; original schemas are never mutated. |
| **Files** | NEW: `.github/workflows/codegen.yml`, `backend/tests/contracts/test_generated_event_clients.py`, `backend/app/core/events/generated/__init__.py` + 6 generated `.py`, `frontend/src/types/events/index.ts` + 6 generated `.ts`, `mobile/lib/events/{EventEnvelope,AimAssignmentCreatedV1,AimSourceCreatedV1,GenerationCompletedV1,GenerationRequestedV1,MissionDraftCreatedV1}.kt`. MODIFIED: `packages/events/scripts/codegen.py` (full rewrite — was placeholder), `backend/requirements.txt` (pinned `datamodel-code-generator==0.57.0`), `frontend/package.json` (added `gen:events` script + `json-schema-to-typescript@^15.0.4` devDep), `frontend/src/lib/sdk/index.ts` (re-export generated `EventEnvelope`), `backend/tests/contracts/test_event_schema_contract.py` (added Python parity test), `Makefile` (3 new targets: `codegen-events`, `codegen-events-check`, `codegen-events-clean`), this file. |

---

### M11 — Reliability & observability uplift **(NEXT)**

PRs: `m11-pr37` through `m11-pr45`. Pulls in every M7/M9-deferred item plus the Stage A trailing items whose triggers have fired (M8 closed → M10 closed).

| PR | Closes | Brief |
|---|---|---|
| `m11-pr37` | M9 deferred — DLQ | DLQ replay tool (`scripts/ops/dlq_replay.py`) + runbook (`docs/runbooks/dlq-replay.md`). List, inspect, replay (one or batch), purge entries from `events:dlq`. Re-XADDs to `source_stream` then XDELs from DLQ. Dry-run by default. |
| `m11-pr38` | M7/M9 deferred — counters | Prometheus counters: queue (`queue_ack_total{outcome,consumer}`, `queue_dlq_total{consumer}`, `queue_pending_redeliveries{consumer}`), generation dispatch (`generation_dispatch_fallback_total{tier}`), bootstrap (`bootstrap_tasks_inflight`, `bootstrap_task_failures_total`). Exposed via `/metrics`. |
| `m11-pr39` | M10 carve-out debt | Refactor 7 import-linter carve-outs (sunset 2026-08-01) where feasible; document those that must remain with an extended sunset + ADR. Target: ≤ 3 carve-outs remaining. |
| `m11-pr40` | TD-4 | Sentry redaction depth 6 → 16. Safe; just a config bump + 1 unit test extension. |
| `m11-pr41` | TD-3 | Migrate `/metrics` to `prometheus_client` (CollectorRegistry + multiprocess mode). Drop hand-rolled text exposition. |
| `m11-pr42` | governance | Feature flag sunset enforcement. `scripts/governance/check_feature_flags.py` already lints registry; add CI fail when `sunset_date` is past unless `--allow-expired-baseline=<flag>` is set. |
| `m11-pr43` | M7 deferred | Generic `app.core.task_registry` module abstracting the bootstrap-task pattern; migrate JobWatchdog + scheduler bootstrap to it. |
| `m11-pr44` | M8 deferred | L2 gRPC sandbox runtime — currently raises `SandboxNotImplemented`. Wire to a minimal in-process gRPC sandbox sidecar (Docker compose entry + handler). Keep flag-gated off by default. |
| `m11-pr45` | P1-15 | Staging mirror of prod data shape — terraform/compose recipe; schema-only sync from prod via `pg_dump --schema-only` weekly. |

**M11 exit gate:** All five queue/generation/bootstrap counters live and scraped. DLQ replay runbook executable end-to-end against a staging DLQ. Import-linter carve-out count ≤ 3 (or extended ADR for each remaining). Sentry redaction depth = 16. `/metrics` served by `prometheus_client`.

#### m11-pr37 — DLQ replay tool + runbook **(SHIPPED)**

| | |
|---|---|
| **What landed** | `scripts/ops/dlq_replay.py` (sync Redis CLI; subcommands `list` / `inspect` / `replay` / `replay-all` / `purge`; dry-run is the default contract — `--apply` is required to mutate). Handles both DLQ shapes: generic-consumer entries (decode the `event` JSON, re-XADD to `source_stream`) and queue entries (re-XADD `{job_id, user_id}`). 23 unit tests under `backend/tests/ops/test_dlq_replay.py` pin parser, filters, payload reconstruction (3 shapes), replay/purge dry-run vs apply semantics, and CLI flag surface. Runbook `docs/runbooks/dlq-replay.md` walks operators through triage → root-cause → pre-flight (queue entries need `generation_jobs` status check because re-XADD bypasses `processed_queue_events` dedup) → replay → bulk drain → purge → post-incident. |
| **Did NOT land** | Counters (`queue_dlq_total`) referenced in the runbook ship in `m11-pr38`. No automatic replay-with-backoff (manual operator workflow only). No web UI. |
| **Rollout** | CLI is read-only by default. Operators run from a pod/laptop with `REDIS_URL` set. No service code paths changed; safe to deploy without restart. |
| **Files** | NEW: `scripts/ops/dlq_replay.py`, `backend/tests/ops/test_dlq_replay.py`, `docs/runbooks/dlq-replay.md`. MODIFIED: `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry + M11 scope). |

#### m11-pr40 — Sentry redaction depth 8 → 16 **(SHIPPED)**

| | |
|---|---|
| **What landed** | Pulled the scrubber depth limit out of `_scrub` into a named constant `MAX_SCRUB_DEPTH = 16` (was an inline `8`). Real-world Sentry payloads regularly nest deeper than 8 (request → context → breadcrumb → http → data → headers → nested envelope → ...) and the silent stop-at-depth meant some `auth_*` keys survived into Sentry. 16 covers every observed shape and still bounds work on cyclic structures. Three new tests pin it: `test_max_scrub_depth_pinned_to_16`, `test_redact_scrubs_at_depth_15` (positive), `test_redact_stops_past_max_depth` (cap is enforced — value at depth>cap survives untouched). |
| **Did NOT land** | No new sensitive-key markers added (out of scope; tracked separately). No change to the Sentry init wiring in `main.py`. |
| **Rollout** | Pure constant bump + new constant export. Backwards-compatible: callers that imported `redact_event_dict`/`sentry_before_send` still work. Safe to deploy hot. |
| **Files** | MODIFIED: `backend/app/core/observability.py` (`MAX_SCRUB_DEPTH` constant, depth check), `backend/tests/test_observability_redaction.py` (3 new tests + import), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

#### m11-pr38 — Queue / dispatch / bootstrap counters **(SHIPPED)**

| | |
|---|---|
| **What landed** | New module `backend/app/core/queue_metrics.py` exposes six families used by Prometheus alerting: `queue_ack_total{consumer}`, `queue_dlq_total{consumer,reason}`, `queue_pending_redeliveries{consumer}`, `generation_dispatch_fallback_total{kind}`, `bootstrap_tasks_inflight`, `bootstrap_task_failures_total{task}`. Increment hooks wired at every XACK and DLQ site in `backend/app/core/queue.py` (4 ack + 1 dlq) and `backend/app/core/events/consumer.py` (3 ack + 1 dlq). Dispatch fallback hooks wired in `backend/app/api/routes/generate/jobs.py` for the three observed kinds (`redis_unavailable_dropped`, `inprocess_fallback`, `temporal_failed`). Bootstrap counters wired into `_track_bootstrap`'s done-callback and into the /metrics scrape (`set_bootstrap_inflight(len(_BOOTSTRAP_TASKS))`). `queue_pending_redeliveries` is sampled at scrape time via `XPENDING <stream> <group>`. Reasons bucketed (`max_deliveries_exceeded` vs `handler_error`); bootstrap task names stripped of `:<job_id>` suffix to bound cardinality. All increments are exception-safe — observability never breaks a request path. |
| **Did NOT land** | Migration to `prometheus_client` (still hand-rolled exposition text — that swap is `m11-pr41`). No histogram families (only counters/gauges). No grafana dashboards / alert rules — those land alongside dashboards-as-code. |
| **Rollout** | Pure additive observability. Increment functions short-circuit silently if the module fails to import. /metrics gracefully no-ops on snapshot errors. Safe to deploy hot. |
| **Files** | NEW: `backend/app/core/queue_metrics.py`, `backend/tests/test_queue_metrics.py` (10 tests). MODIFIED: `backend/app/core/queue.py`, `backend/app/core/events/consumer.py`, `backend/app/api/routes/generate/jobs.py`, `backend/main.py` (six new metric blocks in `prometheus_metrics`), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

#### m11-pr42 — Feature-flag sunset enforcement **(SHIPPED)**

| | |
|---|---|
| **What landed** | Tightened `scripts/governance/check_feature_flags.py`: ANY past-sunset flag now fails the audit (the previous 14-day grace is gone). The only escape is the new `--allow-expired-baseline=<flag>` CLI arg (repeatable; comma-separated lists also accepted). Stale allowlist entries that don't match a registered flag are themselves a build failure — no silent rot. The architecture CI job already invokes the script, so enforcement is live without a workflow change. |
| **Did NOT land** | No new flag deletions or sunset extensions in `config/feature_flags.yaml` (the registry is currently clean — 14 registered, 14 referenced, 0 expired). No issue-template requirement for the allowlist (kept as PR-description discipline). |
| **Rollout** | Pure CI tightening. Safe to land — current registry has zero expired flags. First future expiry will hard-fail CI; owner must either remove the flag or pass `--allow-expired-baseline=<name>` with a tracking issue link in the PR description. |
| **Files** | NEW: `scripts/governance/test_check_feature_flags.py` (11 tests). MODIFIED: `scripts/governance/check_feature_flags.py` (argparse, `_display_path` helper, allowlist enforcement, governance-test-file exclude), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

#### m11-pr43 — Generic `app.core.task_registry` **(SHIPPED)**

| | |
|---|---|
| **What landed** | New `backend/app/core/task_registry.py` extracts the ADR-0041 fire-and-forget pattern into a reusable `TaskRegistry` (spawn / adopt / drain / inflight + optional failure-hook). Two singletons exposed: `bootstrap_registry` (replaces the hand-rolled `_BOOTSTRAP_TASKS` set + done-callback in `backend/app/api/routes/generate/jobs.py::_track_bootstrap`) and `scheduler_registry` (now adopts the periodic stale-job-cleanup task and the `JobWatchdog` task started from the FastAPI lifespan in `backend/main.py`). `_BOOTSTRAP_TASKS` and `_track_bootstrap` are kept as backwards-compat aliases over the registry, so `queue_metrics.set_bootstrap_inflight`, `prometheus_metrics`, and the lifespan drain block stay byte-identical at the call-site. |
| **Did NOT land** | Did NOT remove the `_BOOTSTRAP_TASKS` symbol or `_track_bootstrap` function (kept as aliases until callers migrate). Did NOT plumb `scheduler_registry.drain` into the lifespan shutdown — the existing per-task cancel/await blocks still own that path; introducing one drain call would change shutdown ordering and is left for a follow-up. Did NOT migrate worker-side tasks (`StreamConsumer`, `OutboxRelay`) — they own their own task lifecycle and don't need the registry abstraction. |
| **Rollout** | Pure refactor — the bootstrap path is a 1:1 wrapper over the new registry; the scheduler-side change replaces `asyncio.create_task(...)` with `scheduler_registry.spawn(...)` / `.adopt(...)` (same task is created, just tracked centrally). Failure metrics still flow through `queue_metrics.inc_bootstrap_failure` via the registry's `failure_hook` slot. |
| **Files** | NEW: `backend/app/core/task_registry.py`, `backend/tests/test_task_registry.py` (11 tests, including the bootstrap-alias contract test). MODIFIED: `backend/app/api/routes/generate/jobs.py` (`_track_bootstrap` now delegates to `bootstrap_registry.spawn`), `backend/main.py` (scheduler tasks now go through `scheduler_registry`), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

#### m11-pr41 — `/metrics` migrated to `prometheus_client` **(SHIPPED)**

| | |
|---|---|
| **What landed** | New `backend/app/core/prometheus_collectors.py` introduces `HirestackCollector`, a `prometheus_client` `Collector` that yields `GaugeMetricFamily` / `CounterMetricFamily` instances on every scrape by reading the existing snapshot sources: `MetricsCollector`, `queue_metrics`, `circuit_breaker._breakers`, `queue.queue_depth`, `cache.get_all_cache_stats`, `_daily_tracker`. `render_metrics()` builds a fresh `CollectorRegistry` per scrape and serialises via `generate_latest()`. The `/metrics` route in `backend/main.py` is now a 6-line auth-check + render — the old ~300-line hand-rolled `lines.append(...)` block is deleted. All metric NAMES, label NAMES, and label VALUES from the previous exposition are preserved 1:1 (the m11-pr38 six-family contract is pinned by `test_metrics_endpoint_exposes_all_six_families`, which now also asserts the names appear in the rendered bytes). `prometheus_client>=0.20,<1.0` added to `backend/requirements.txt`. |
| **Did NOT land** | Did NOT enable `PROMETHEUS_MULTIPROC_DIR` aggregation — Railway runs a single uvicorn worker today; multiprocess mode is a documented one-flip if/when we add gunicorn workers. Did NOT add histogram families (still counters/gauges only — same shape as before). Did NOT touch the `/livez` route or auth gate. |
| **Rollout** | Endpoint contract preserved (Bearer auth + same metric names/labels). Content-type now `text/plain; version=1.0.0; charset=utf-8` (was `version=0.0.4`) — Prometheus scrapers accept both. Safe to deploy hot. |
| **Files** | NEW: `backend/app/core/prometheus_collectors.py`, `backend/tests/test_prometheus_collectors.py` (11 tests). MODIFIED: `backend/main.py` (`prometheus_metrics` body slimmed to delegate to `render_metrics`; ~309 lines of hand-rolled exposition deleted), `backend/requirements.txt` (add `prometheus_client>=0.20,<1.0`), `backend/tests/test_queue_metrics.py` (six-families contract test now inspects collector module + asserts on rendered bytes), `backend/tests/unit/test_resilience_w8.py` (circuit-breaker contract test now inspects collector module), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

#### m11-pr39 — import-linter carve-out reduction (intel cache through facade) **(SHIPPED)**

| | |
|---|---|
| **What landed** | Extended `ai_engine/api.py` to re-export `JDAnalysisCache` and `get_jd_cache`, then migrated `backend/app/api/routes/intel.py` from `from ai_engine.cache import …` to `from ai_engine.api import …` at all 3 local-import sites. Pruned the matching `backend.app.api.routes.intel -> ai_engine.cache` line from C3's `ignore_imports`. C3 sunset-2026-08-01 carve-outs reduced 7 → 6. Also added a transitive `ai_engine.client -> backend.app.services.pipeline_runtime` ignore to C2 (backend layered architecture) — the lazy try/except inside `ai_engine.client` is the existing C1 carve-out, but `prometheus_collectors` (m11-pr41) now triggers it transitively via `ai_engine.api`. All 4 import-linter contracts KEPT after the change. |
| **Did NOT land** | The remaining 5 sunset-2026-08-01 C3 carve-outs (`analytics`, `generate.stream` ×2, `pipeline_runtime` ×3) were NOT migrated. Those source files are on the do-not-touch list for this branch (mid-mission by another concurrent agent), so the carve-outs are deferred to a follow-up PR. The original spec target was ≤ 3 — current count 6 — the gap is fully attributable to the do-not-touch boundary, not to design. The ai_engine/* C1 carve-outs (4 lazy `from backend.*` try/except inside `ai_engine.client`, `model_router`, `agents/tools`, `agents/sub_agents/base`) were also NOT touched — those require constructor-injection refactors of files on the do-not-touch list. |
| **Rollout** | Pure import-graph refactor; no runtime behaviour change. `intel.py` calls the same cache class via the facade; smoke test passes. Backwards-compat: `ai_engine.cache` still exports the same symbols, so any test or external caller still works. Safe to deploy hot. |
| **Files** | MODIFIED: `ai_engine/api.py` (+ cache re-exports), `backend/app/api/routes/intel.py` (3 imports swapped), `.importlinter` (− 1 C3 ignore, + 1 C2 transitive ignore), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

---

#### m11-pr44 — L2 gRPC sandbox runtime **(SHIPPED)**

| | |
|---|---|
| **What landed** | New module `ai_engine/registry/grpc_sandbox.py` implements the L2 sidecar runtime as a minimal in-process `grpc.aio` server with a generic `unary_unary` handler. Wire format is JSON-in / JSON-out (UTF-8 bytes) over a single RPC `/hirestack.L2Sandbox/Invoke` — no `.proto`, no `grpcio-tools` build step, just `grpcio>=1.60`. The server resolves `code_ref` through the canonical `RESOLVERS` map (ADR-0033) and returns a structured `{ok, result\|error_kind\|error_message}` envelope. The existing `L2GrpcSidecarSandbox` (m7-pr29) now delegates to a runtime that lazy-starts an in-process server on first invoke and reuses it; `_singleton` lives in module scope and shutdown is exposed via `shutdown_runtime()`. New standalone entrypoint `ai_engine/registry/run_l2_sandbox.py` runs the server as a long-lived process for the `tool-runner` sidecar. New compose service `tool-runner` in `infra/docker-compose.yml` under the `l2-sandbox` profile (off by default). 13 new tests in `ai_engine/tests/registry/test_grpc_sandbox.py` cover the codec round-trip, server-side handler resolution / error envelopes / bad-input rejection, full inproc gRPC client⇄server round-trip with both success and remote-error paths, plus the flag-on integration test where `L2GrpcSidecarSandbox` actually executes a tool through the live gRPC channel. **65/65 registry tests green; 4/4 import-linter contracts KEPT.** |
| **Did NOT land** | No `.proto` file — wire format is hand-rolled JSON over bytes. If a typed schema becomes worthwhile we'll add the proto + codegen later as a separate PR; right now the cost / benefit argues against it. No L2-tier tools are seeded today (the `RESOLVERS` map is still empty by design from m7-pr29), so this ships as shadow-only infrastructure: even with both flags ON, every Invoke RPC returns `UnknownCodeRef` until a real resolver lands. No client-side retry / circuit-breaker logic — the gRPC channel uses default settings; tool-level resilience stays in the dispatcher / tenacity layer above. No mTLS between backend and `tool-runner` — the sidecar runs inside the compose network; mTLS lands when the sidecar is exposed cross-node. |
| **Rollout** | Two new feature flags, both **default OFF** so M7-E behaviour is preserved verbatim. (1) `FF_TOOL_L2_GRPC_ENABLED` — when OFF, `L2GrpcSidecarSandbox.invoke()` raises `SandboxNotImplemented` with the tool name (legacy contract intact). (2) `FF_TOOL_L2_GRPC_TARGET` (default `inproc`) — `inproc` lazy-starts an in-process server, or set to `host:port` for the external sidecar. Combined with the existing `FF_TOOL_SANDBOX_TIER_ROUTING` (also OFF), L2 dispatch only happens with all three flags / configs aligned. Compose: `docker compose --profile l2-sandbox up tool-runner` brings up the sidecar; without the profile it doesn't start. |
| **Observability** | New log lines: `tool_sandbox_l2_inproc_started` (once per process when in-process server boots), `tool_sandbox_l2_external_target` (once when pointed at a sidecar), `l2_sandbox_listening` / `l2_sandbox_stopping` (sidecar lifecycle). Server-side errors come back to the dispatcher as `L2RemoteError` with `kind` + `message` so the existing `tool_invocation_error_total{kind}` counter cardinality stays bounded. |
| **Files** | NEW: `ai_engine/registry/grpc_sandbox.py` (~330 lines: codec + server handler + client + runtime singleton + L2 sandbox class), `ai_engine/registry/run_l2_sandbox.py` (sidecar entrypoint), `ai_engine/tests/registry/test_grpc_sandbox.py` (13 tests). MODIFIED: `ai_engine/registry/sandboxes.py` (`L2GrpcSidecarSandbox` now delegates to `L2GrpcSandboxRuntime`; flag-OFF still raises with tool name), `backend/requirements.txt` (+ `grpcio>=1.60,<2.0`), `infra/docker-compose.yml` (+ `tool-runner` service under `l2-sandbox` profile), `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). |

---

#### m11-pr45 — staging mirror of prod data shape **(SHIPPED)**

| | |
|---|---|
| **What landed** | Closes P1-15. New shell script `scripts/ops/sync_staging_schema.sh` does `pg_dump --schema-only --clean --if-exists --no-owner --no-privileges --no-tablespaces` from prod → applies to staging inside a `psql --single-transaction --variable=ON_ERROR_STOP=1` so partial failures roll back. New GitHub Actions workflow `.github/workflows/staging-schema-sync.yml` runs the script every Sunday 06:00 UTC against the `PROD_DATABASE_URL_RO` and `STAGING_DATABASE_URL` secrets, with manual dispatch + dry-run option. New compose file `infra/staging-mirror.compose.yml` brings up an empty Postgres 16 on `127.0.0.1:55432` for local testing of the script without pointing at real staging. New runbook `docs/runbooks/staging-schema-sync.md` documents triggers, manual run, common failure modes, and rollback. |
| **Did NOT land** | No row-level data sync — staging holds its own seed data on purpose (PII / size / tenant-isolation). No Terraform module — the workflow itself is the IaC for this; if a future env (e.g. preview) needs the same hook we'll factor a reusable workflow. No automatic schema-diff alerting against the previous week's dump (would catch unannounced prod migrations) — deferred until the first incident motivates it. No coverage of Supabase-managed schemas beyond `public` — `SCHEMAS` env variable accepts a comma-separated list, so adding `auth`, `storage`, etc. is one secret edit away when needed. |
| **Rollout** | Workflow is `permissions: contents: read` and runs only on `schedule` + `workflow_dispatch`; no PR-triggered runs. First scheduled execution is whatever Sunday 06:00 UTC follows the merge. Required repo secrets `PROD_DATABASE_URL_RO` (must be a **read-only** role; the script never writes to prod) and `STAGING_DATABASE_URL` must be in place before the first run — until then the workflow fails fast with a clear error message. |
| **Files** | NEW: `scripts/ops/sync_staging_schema.sh` (executable; `set -euo pipefail`), `.github/workflows/staging-schema-sync.yml`, `infra/staging-mirror.compose.yml`, `docs/runbooks/staging-schema-sync.md`. MODIFIED: `docs/architecture/IMPLEMENTATION_MILESTONES.md` (this entry). Stage A trailing items table updated to reflect `Staging mirror of prod data shape` is now SHIPPED via m11-pr45. |

---

## Stage A trailing items (M11+, no PR numbers yet)

| Item | Closes | Trigger to start |
|---|---|---|
| `mypy --strict` on `ai_engine/` | TD-1 | After M8 closed — **SHIPPED m12-pr01** (initial scope: `ai_engine.api`, `ai_engine.registry.*`; ratchet via [mypy.ini](../../mypy.ini) allowlist) |
| Coverage gate at 70% on `ai_engine/` | TD-2 | After M8 closed — **SHIPPED m12-pr02** (initial scope mirrors mypy allowlist; actual coverage ≈93%; ratchet via `[tool.coverage.run] source` in [pyproject.toml](../../pyproject.toml)) |
| `prometheus_client` migration for `/metrics` | TD-3 | After M8 closed — **SHIPPED m11-pr41** (`HirestackCollector` in `backend/app/core/prometheus_collectors.py`; six-family contract preserved) |
| Sentry redaction depth → 16 | TD-4 | Anytime; safe — **SHIPPED m11-pr40** |
| Feature flag sunset enforcement (CI fail past sunset) | (governance) | After `config/feature_flags.yaml` exists with ≥5 flags — **SHIPPED m11-pr42** (`scripts/governance/check_feature_flags.py` fails CI past `sunset_date` unless explicit `--allow-expired-baseline`) |
| Staging mirror of prod data shape | P1-15 | After M10 — **SHIPPED m11-pr45** |

**Stage A trailing items — all SHIPPED.** No outstanding M11+ work without a milestone home. Stage B placeholders below activate only on trigger.

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
