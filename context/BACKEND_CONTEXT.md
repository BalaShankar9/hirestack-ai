---
title: Backend Context
last_synced: 2026-05-08
watch_paths:
  - backend/main.py
  - backend/app
  - backend/requirements.txt
  - backend/pytest.ini
  - Procfile
canonical_sources:
  - backend/main.py
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#4-bounded-contexts--ownership
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#7-workflow-durability-temporal
update_when:
  - middleware order in backend/main.py changes
  - a new route family is added (new file in backend/app/api/routes/)
  - a new service module is added under backend/app/services/
  - a new Temporal workflow is added under backend/app/temporal/workflows/
  - the Procfile process list changes
---

# Backend Context

> One process boundary, four runtimes. The FastAPI app served by `api` plus
> three sibling processes (`worker`, `scheduler`, `temporal_worker`) all
> import the same `backend.app` package. The boundary contract is in
> [`Procfile`](../Procfile).

---

## TL;DR — 12 lines

1. **Single Python entrypoint:** [`backend/main.py`](../backend/main.py).
   The legacy `backend/app/main.py` was retired (P1-6 SHIPPED).
2. **Four processes** declared in [`Procfile`](../Procfile): `api` (uvicorn
   FastAPI), `worker` (Redis Streams consumer), `scheduler` (cron-like
   maintenance), `temporal_worker` (Temporal Cloud worker for workflows
   and activities).
3. **FastAPI 0.115–0.130** with **Pydantic v2** and `pyjwt 2.12+`
   (closes CVE-2026-32597). All HTTP I/O is async.
4. **Middleware order is load-bearing.** SecurityHeaders → SlowAPI
   (rate limit) → JWT auth → UsageGuard (cost cap) → BillingCheck
   (fail-closed) → Idempotency. See `backend/main.py` for the exact stack.
5. **50+ route files** under `backend/app/api/routes/`. Every user-facing
   route has a `@limiter.limit(...)` decorator (246 across 46 of 48 route
   files; the two exceptions are health and metrics).
6. **60+ service modules** under `backend/app/services/`. Services are
   plain async Python classes/functions; no inheritance hierarchy required.
7. **Generation orchestrator** is `services/pipeline_runtime.py`. It picks
   one of three execution paths (Temporal → Redis → in-process) by checking
   `ff_inprocess_fallback` and Temporal connectivity.
8. **All AI calls cross the `ai_engine.api` boundary.** Routes/services
   never import `ai_engine.agents.*` directly; they call
   `ai_engine.api.run_stage()` / `run_chain()` / `run_pipeline()`.
9. **Outbox pattern for events.** `backend/app/core/events/OutboxWriter`
   writes to `events_outbox` in the same transaction as the state change;
   `worker` relays to Redis Streams; consumers ACK on success only (P0-3).
10. **Temporal Cloud** hosts long-running workflows (~11 defined; see
    blueprint §7.1). Per-stage activities (P1-1) checkpoint after every
    agent so a crash does not re-burn tokens.
11. **Observability:** OpenTelemetry → Grafana / Honeycomb (traces,
    metrics), structlog (JSON logs to stdout → Sentry), Langfuse (LLM
    traces). Sentry redaction depth = 16 (TD-2 SHIPPED).
12. **Tests:** 251 pytest files. `pytest 9.0.3+` (closes CVE-2025-71176)
    with `pytest-asyncio`, `pytest-timeout` (30s default), `pytest-xdist`
    (parallelism). Run pattern: `cd backend && pytest <path> --no-cov -q`.

---

## The four processes (`Procfile`)

```
api:             uvicorn backend.main:app --host 0.0.0.0 --port $PORT
worker:          python -m backend.app.workers.event_consumer
scheduler:       python -m backend.app.workers.scheduler
temporal_worker: python -m backend.app.temporal.worker
```

| Process | Role | Scaling unit |
|---|---|---|
| `api` | HTTP + SSE; serves users + admin + webhooks | Horizontally scaled by Railway. Stateless except SSE sessions (in-memory; durable replay TODO). |
| `worker` | Consumes Redis Streams (`generation.*`, `aim.*`, etc.); ACKs on success only | One per stream consumer group; rebalance on add/remove. |
| `scheduler` | Cron-like: partition health, stale job sweep, cost reconciliation | Singleton (advisory lock). |
| `temporal_worker` | Polls Temporal Cloud task queue; runs workflows + activities | Horizontally scaled; Temporal handles distribution. |

All four import `backend.app.*`; nothing is duplicated across processes.

---

## Middleware stack (`backend/main.py`)

Order matters because each layer mutates `request.state` or short-circuits:

```
[outer]
SecurityHeadersMiddleware    -- HSTS, CSP, X-Content-Type-Options, X-Frame-Options
                                Forbids inline script except dev. ADR-0017.
CORSMiddleware               -- allowlist driven by ENVIRONMENT
SlowAPIMiddleware            -- Redis-backed token bucket; required in prod.
                                Routes apply @limiter.limit("60/minute") etc.
JWTAuthMiddleware            -- verifies Supabase JWT (RS256/HS256).
                                Sets request.state.user = {org_id, user_id, cell_id, role}
                                Skips: /health, /metrics, /openapi.json, /docs, /webhooks/*
UsageGuardMiddleware         -- per-org daily $ cap (P0-4 SHIPPED m12-pr08).
                                Reads cost from `org_cost_hourly` MV; raises 402.
BillingCheckMiddleware       -- plan / quota check; fail-closed in production
                                (TD-7 SHIPPED m12-pr11). BILLING_FAIL_CLOSED env override.
IdempotencyMiddleware        -- POST/PATCH/DELETE with Idempotency-Key header.
                                Hits idempotency_keys table (24h TTL).
                                Replays cached response on duplicate key.
[inner]
                              -- Route handler runs here.
```

Adding a new middleware requires an ADR if it changes header semantics or
the security posture. Reordering is a breaking change for clients.

---

## Routes inventory

`backend/app/api/routes/` contains 50+ files. Each is a thin layer that:

1. Validates input (Pydantic).
2. Resolves dependencies (auth, DB session) via `api/deps.py`.
3. Calls a service in `app/services/`.
4. Maps service exceptions to HTTPException with safe messages.
5. Returns a Pydantic response model.

Route file naming maps 1:1 to dashboard surfaces in the frontend. Highlights:

| Route file | Purpose |
|---|---|
| `auth.py` | login, register, password reset, email verify |
| `applications.py` | CRUD on user applications |
| `generate/jobs.py` | **TD-1: 1500+ lines.** Job-based generation entrypoint. Splitting planned. |
| `generate/stream.py` | streaming generation (when ff_streaming on) |
| `generate/sync.py` | synchronous generation (legacy / fallback) |
| `agentic_stream.py` | SSE for Mission-Control. P0-7 SHIPPED: replay endpoint. |
| `sse.py` | generic SSE primitives |
| `billing.py` | subscription, usage, invoices |
| `usage.py` | per-org usage counters (read-only) |
| `api_keys.py` | API key CRUD (Stage B) |
| `webhooks.py` | inbound webhooks (Stripe, Supabase) |
| `candidates.py` | agency Kanban CRUD |
| `orgs.py` | org CRUD; cell move triggers `CellMigrationWorkflow` |
| `users.py` | user profile / preferences |
| `evidence.py` | evidence ledger (verbatim > derived > inferred > user_stated) |
| `gaps.py`, `insights.py` | gap analysis + benchmark comparisons |
| `ats_scanner.py` | ATS scoring of generated CV |
| `interview.py` | interview simulator session CRUD + signals |
| `salary.py` | salary coach analyses |
| `learning.py` | learning streaks |
| `ppt.py` | slide-deck generation |
| `tracked_companies.py` | watchlist + auto-prep |
| `job_sync.py` | external job board pull |
| `aim.py` | Application Intelligence Module |
| `culture_fit.py`, `networking.py`, `linkedin.py` | per-domain agent surfaces |
| `mission.py` | mission control orchestration |
| `health.py`, `metrics.py` | infra (no auth, no rate limit) |

The full list is in `backend/app/api/routes/`. Each file's `router` is
mounted in `backend/main.py`.

---

## Services layer

`backend/app/services/` holds business logic as plain async functions and
classes. Naming: `<domain>.py` or `<domain>/__init__.py` for larger.

Load-bearing services:

| Service | Role |
|---|---|
| `pipeline_runtime.py` | picks Temporal/Redis/in-process; emits `pipeline.execution.path` trace attribute |
| `usage_guard.py` | per-org $ cap (P0-4); cascade-failure breaker; raises `OrgDailyCostCapExceeded` |
| `cost_attribution.py` | reads `org_cost_hourly` MV; supplies `usage_guard` and dashboards (P1-8) |
| `billing.py` | Stripe + plan/quota; fail-closed in prod (TD-7 SHIPPED m12-pr11) |
| `feature_flag_audit.py` | append-only audit table (P1-9 SHIPPED m12-pr09) |
| `idempotency.py` | implements the middleware; manages 24h TTL keys |
| `event_publisher.py` | wraps `OutboxWriter` for service-level callers |
| `ats_scanner.py`, `interview.py`, `salary.py`, ... | per-domain logic |

The blueprint §4.1 maps services to bounded contexts. Cross-context calls
are visible in `import-linter` reports.

---

## Temporal workflows

Defined in `backend/app/temporal/workflows/`. Activities in
`backend/app/temporal/activities/`.

11 workflows (blueprint §7.1):

| Workflow | Type | Purpose |
|---|---|---|
| `GenerationWorkflow` | one-shot | one application generation |
| `LongLivedSessionWorkflow` | actor | multi-turn agent w/ signals (e.g. interview sim) |
| `OrgOnboardingWorkflow` | one-shot | provisioning, sample data, first-run guidance |
| `PartitionMaintenanceWorkflow` | cron | DB partition health (uses `pg_partman`) |
| `EventArchiveWorkflow` | cron | monthly outbox → S3 Parquet |
| `DLQReplayWorkflow` | manual | operator-controlled event replay |
| `CellMigrationWorkflow` | one-shot | move org between cells |
| `BillingReconciliationWorkflow` | cron | reconcile usage_guard counters with `ai_invocations` |
| `EvalRegressionWorkflow` | cron | nightly gold-set re-run + alert |
| `ChaosWorkflow` | cron | inject controlled failures (gameday) |
| `DRDrillWorkflow` | quarterly | DR restore + smoke pipeline |

Per-stage activity model (P1-1 SHIPPED — m8-pr32):

```python
@workflow.defn
class GenerationWorkflow:
    @workflow.run
    async def run(self, brief: GenerationInput) -> None:
        for phase in PIPELINE_PHASES:
            await workflow.execute_activity(
                run_stage_activity,
                args=[phase, brief, self._previous_outputs],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
```

Each activity reads the idempotency token from `generation_job_events`
before doing any LLM work, so a Temporal retry does not re-burn tokens.

---

## Event taxonomy & outbox

- ~30 canonical event types declared in
  [`packages/events/schema/v1/`](../packages/events/schema/v1/).
- 5 v1 events shipped: `aim.assignment.created`, `aim.source.created`,
  `generation.requested`, `generation.completed`, `mission.draft.created`.
- Producers call `OutboxWriter.append(event_type, payload, org_id)` in the
  same transaction as the state change.
- `worker` polls `events_outbox` with `FOR UPDATE SKIP LOCKED`, publishes
  to Redis Streams, marks `delivered_at`.
- Consumers ACK on success only (P0-3 SHIPPED m7-pr27c). Poison messages
  go to DLQ; replay via `DLQReplayWorkflow`.
- Strict event-payload validation at `OutboxWriter.append` (P1-2 SHIPPED
  m7-pr31): unknown event type or schema mismatch raises immediately.

---

## Observability (per blueprint §13)

| Pillar | Tool | Notes |
|---|---|---|
| Traces | OpenTelemetry → Grafana Cloud / Honeycomb | every route + service span; `pipeline.execution.path` attribute |
| Metrics | Prometheus text format from `/metrics` (TD-3: hand-rolled, planned to switch to OTEL metrics) | golden SLOs |
| Logs | structlog JSON to stdout → Sentry → Grafana | redaction depth 16 (TD-2 SHIPPED) |
| Errors | Sentry (`sentry-sdk[fastapi]`) | per-process; before-send scrubs PII |
| LLM | Langfuse (`langfuse>=2.40`) | one trace per `ai_invocations` row |

Per blueprint §13.2, every code path emits at least one of `(metric, log,
trace, event)`. Reviewers reject PRs that introduce a new path without it.

---

## Feature flags (`config/feature_flags.yaml`)

Twelve+ production flags. Each row has `owner / created / sunset / default
/ purpose`. Sunset enforced by
[`scripts/governance/check_feature_flags.py`](../scripts/governance/check_feature_flags.py)
— CI fails if a flag is past sunset by 14 days.

Mandatory flags (default value listed):

| Flag | Default | Purpose |
|---|---|---|
| `ff_temporal_generation` | true | route generations via Temporal |
| `ff_tool_registry` | true | use jsonschema-validated tool registry |
| `ff_queue_ack_on_success` | true | P0-3 ACK behaviour |
| `ff_temporal_per_stage` | true | per-stage activities (P1-1) |
| `ff_inprocess_fallback` | **false in prod** | last-resort path; ADR-0038 keeps this off |
| `ff_aim_rag` | true | AIM uses RAG |
| `ff_event_consumer` | true | worker process consumes |
| `ff_outbox_relay` | true | outbox → Redis Streams relay |
| `ff_strict_critic_gate` | true | Sentinel hard-fails on critic failure |
| `ff_tool_capability_tokens` | true | enforce capability tokens (P0-5) |
| `ff_tool_sandbox_tier_routing` | true | route by `sandbox_tier` |
| `ff_anthropic_provider` | true | enable Claude in cascade tail (P1-4) |
| `ff_ai_invocations_recorder` | true | write `ai_invocations` rows |
| `ff_strict_event_validation` | true | validate event payloads at OutboxWriter |

All flag flips are auto-snapshotted into `feature_flag_audit` (P1-9).

---

## Running the backend locally

```
cd "<repo root>"
source .venv/bin/activate
export DATABASE_URL=...           # supabase or local Postgres
export REDIS_URL=...
export TEMPORAL_ADDRESS=...
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...      # optional; gates ff_anthropic_provider
uvicorn backend.main:app --reload --port 8080
```

Or via docker-compose: `docker compose -f infra/docker-compose.yml up`.

---

## Test conventions

```
cd "<repo root>"
source .venv/bin/activate
pytest backend/tests/<path> --no-cov -q          # single area
pytest backend -n auto -q                        # full suite (xdist)
pytest backend -k provider_failover -q           # filtered
```

`--no-cov` is necessary while iterating because the coverage gate slows
single-file runs. CI uses `pytest -n auto --cov` with the gate enforced
(P1-10 SHIPPED).

Mandatory contract tests:

- `backend/tests/security/test_tenancy_isolation.py` — must stay green; no
  RLS regressions allowed.
- `backend/tests/contracts/test_event_schema_contract.py` — every event
  type used in code must have a matching JSON schema.
- `backend/tests/ai/test_provider_failover.py` (m12-pr12 SHIPPED) — proves
  blueprint §21 "single Gemini outage" guarantee.

---

## What "good backend" looks like in this repo

- [ ] New route uses `Depends(get_current_user)` and `Depends(get_db)`.
- [ ] New route has `@limiter.limit(...)` (unless health/metrics).
- [ ] New service is async, has unit tests, raises typed exceptions
      (mapped to HTTPException at the route).
- [ ] State changes go through `OutboxWriter` for any cross-process effect.
- [ ] AI calls go through `ai_engine.api.*`, not `ai_engine.agents.*`.
- [ ] Long-running work goes through Temporal, not in-process.
- [ ] New table has RLS enabled in the same migration.
- [ ] New code emits at least one of `(metric, log, trace, event)`.
- [ ] Pinned dependency: floor closes a CVE, ceiling avoids silent break.
