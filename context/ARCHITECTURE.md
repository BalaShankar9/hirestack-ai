---
title: Architecture
last_synced: 2026-05-08
watch_paths:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md
  - docs/ARCHITECTURE.md
  - backend/main.py
  - backend/app/main.py
  - ai_engine/api.py
  - ai_engine/__init__.py
  - Procfile
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md
  - docs/ARCHITECTURE.md
  - docs/adrs/
update_when:
  - a new deployable is added (e.g. realtime-gateway-svc)
  - a bounded context is split / merged
  - the import-linter contracts change
  - a new ADR with status "Accepted" lands
  - the request lifecycle (auth -> middleware -> route -> service -> AI) changes
---

# Architecture

> The single canonical engineering constitution is the **Architecture
> Blueprint**: [`docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](../docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md)
> (~1200 lines, 25 sections). This file is the **map** to it — pointers,
> shape, lifecycle, and the rules new code must follow. When this file and
> the blueprint disagree, the blueprint wins.

---

## TL;DR — 12 lines

1. **One repo, four backend deployables, one frontend.** `api`, `worker`,
   `scheduler`, `temporal_worker` (declared in [`Procfile`](../Procfile))
   plus `web` on Netlify.
2. **Modular monolith with bounded contexts** enforced by `import-linter`
   (blueprint §4.2). Five contexts: identity, billing, orchestration, AI
   runtime, eventing.
3. **`ai_engine/` is library-only.** It MAY NOT import from `backend.app`.
   The boundary is the public surface in [`ai_engine/api.py`](../ai_engine/api.py).
4. **Three execution paths for generation,** in priority order:
   Temporal → Redis Streams → in-process asyncio. The third is gated by
   `ff_inprocess_fallback` (default off in production per ADR-0038).
5. **Postgres is the source of truth.** Redis is a cache/bus only. Anything
   important goes through the **outbox pattern** (`events_outbox` →
   `event-relay` → consumers).
6. **Workflow durability lives in Temporal Cloud,** not in code. Per-stage
   activities (P1-1, m8-pr32) checkpoint after every agent so a crash
   resumes from the last green stage rather than re-burning tokens.
7. **AI calls go through `model_router`** which selects provider × model by
   task profile, budget, provider health, input length. Single-provider
   dependency is forbidden in production (P1-4 SHIPPED — m7-pr28).
8. **Tools execute in tiered sandboxes** L0/L1/L2/L3 (blueprint §6.3). Every
   tool invocation requires a `CapabilityToken` (P0-5 SHIPPED — m7-pr29).
9. **Streaming UI is SSE** with `Last-Event-ID` resumption (P0-7 SHIPPED —
   m12-pr05). EventSource is forbidden in the frontend; only the wrapped
   client in [`frontend/src/lib/sseClient.ts`](../frontend/src/lib/sseClient.ts)
   is allowed.
10. **All multi-tenant tables enforce RLS** keyed on `org_id`. 64/64 tables
    today. CI test `tests/security/test_tenancy_isolation.py` runs on every
    PR.
11. **Cell architecture protocol is wired now,** even with one cell. JWTs
    carry a `cell_id` claim; routing uses a global `org_id → cell_id`
    table. Adding a second cell becomes config, not rewrite.
12. **Five Architectural Principles** govern every decision (blueprint §1):
    P1 Durability > throughput · P2 Contracts > coordination · P3 Cells >
    clusters · P4 Boring infra, opinionated runtime · P5 Observability is
    build-time.

---

## Component map

```
                                Netlify CDN
                                     |
                                     v
                          +-----------------------+
                          | Next.js 14 App Router |
                          |  (frontend/src/**)    |
                          +-----+--------+--------+
                       fetch    |   SSE   |   Supabase JS (auth + storage)
                                |        |
                                v        v
                  +-----------------------------------+
                  |  api  (FastAPI, backend/main.py)  |
                  |  - middleware stack (security ->  |
                  |    JWT -> usage_guard -> billing  |
                  |    -> idempotency -> slowapi)     |
                  |  - 50+ route files                |
                  |  - 60+ services                   |
                  +-----+----------+----------+-------+
                        |          |          |
                  Postgres    Redis       Temporal Cloud
                  (Supabase)  (Upstash)   (workflows)
                        |          |          |
                        |          |          v
                        |          |   +------------------+
                        |          |   | temporal_worker  |
                        |          |   | (workflows +     |
                        |          |   |  activities)     |
                        |          |   +--------+---------+
                        |          |            |
                        |          |            v
                        |          |     ai_engine library
                        |          |     (chains/, agents/)
                        |          v
                        |   +-----------------+
                        |   | worker          |
                        |   | (Redis Streams  |
                        |   |  consumer for   |
                        |   |  outbox events) |
                        |   +-----------------+
                        |
                        v
                  +-----------------+
                  | scheduler       |
                  | (cron-style:    |
                  |  partition mgmt,|
                  |  stale jobs,    |
                  |  cost recon)    |
                  +-----------------+
```

The blueprint §3 has the full ASCII diagrams for **current** topology and
**Stage B target** topology (with realtime-gateway-svc, knowledge-svc,
identity-svc, event-relay-svc and Kafka added). When designing new code,
sketch where it sits in **both** diagrams; the same code should not require
rewriting at Stage B.

---

## The five Architectural Principles

Every architectural choice is a corollary of one of these five principles.
Disagreement requires an ADR.

| # | Principle | Practical consequence |
|---|---|---|
| **P1** | **Durability > throughput.** | Postgres is source of truth. Outbox > direct fanout. Temporal for long work. |
| **P2** | **Contracts > coordination.** | JSON Schema + OpenAPI + import-linter > meetings. Producers and consumers never share types via duck typing. |
| **P3** | **Cells > clusters.** | One Postgres + Redis + Temporal namespace + S3 prefix per `(region, shard)`. JWT carries `cell_id`. Splitting a cell is config, not rewrite. |
| **P4** | **Boring infra, opinionated runtime.** | Postgres + Redis + Temporal everywhere. The smarts are in `ai_engine/`. |
| **P5** | **Observability is build-time, not runtime.** | If a code path doesn't emit `(metric, log, trace, event)` it doesn't merge. |

---

## Bounded contexts and ownership

From blueprint §4. Enforced in CI by `import-linter` (`pyproject.toml`):

| Context | Owns | Code (today) | Future split |
|---|---|---|---|
| **Identity & Tenancy** | users, orgs, RBAC, JWT, RLS, cell routing | `backend/app/api/deps.py`, supabase auth | `identity-svc` (Stage B) |
| **Billing & Cost** | plans, budgets, usage counters, cost attribution | `backend/app/services/usage_guard.py`, billing routes | `billing-svc` (Stage B) |
| **Generation Orchestration** | application brief, pipeline, stages, runs | `backend/app/services/pipeline_runtime.py`, `ai_engine/chains/` | `orchestration-svc` (Temporal worker) |
| **AI Runtime** | model routing, retries, breakers, tool dispatch | `ai_engine/` | stays as library + `tool-runner` sidecar |
| **Knowledge & RAG** | ingestion, vector store, retrieval | `ai_engine/data/` (partial) | `knowledge-svc` (Stage B) |
| **Realtime** | SSE/WS, presence, pipeline progress | scattered in routes | `realtime-gateway-svc` (Stage A end) |
| **Eventing** | outbox, schemas, relay, DLQ, archival | `backend/app/core/events/`, `packages/events/` | shared library + `event-relay-svc` |
| **Content Storage** | resumes, JDs, generated docs | Supabase Storage | unchanged |
| **Public API** | thin HTTP layer | `backend/app/api/routes/` | `api-gateway-svc` (Stage B) |

The CODEOWNERS section in blueprint §4.3 maps these to teams. Single-engineer
team today means everything routes to the founder; this exists to be ready,
not because it gates anything yet.

---

## The three execution paths

Generation can run via three paths, in this priority order:

1. **Temporal Cloud** — preferred for any user-facing generation. Per-stage
   activities (P1-1) provide checkpointing. Workflows: `GenerationWorkflow`,
   `LongLivedSessionWorkflow`, `OrgOnboardingWorkflow`,
   `PartitionMaintenanceWorkflow`, `EventArchiveWorkflow`,
   `DLQReplayWorkflow`, `CellMigrationWorkflow`,
   `BillingReconciliationWorkflow`, `EvalRegressionWorkflow`,
   `ChaosWorkflow`, `DRDrillWorkflow`. Defined in `backend/app/temporal/`.
2. **Redis Streams** — fallback when Temporal connection is unavailable.
   ACK on success only (P0-3). DLQ for poison messages.
   `backend/app/core/queue.py`.
3. **In-process asyncio** — last-resort fallback gated by
   `ff_inprocess_fallback`. **Default OFF in production** per ADR-0038
   (W2 risk: single-pod OOM). Only for local dev / smoke.

A single user request always hits exactly one path. The chosen path is
emitted as `pipeline.execution.path = (temporal | redis | inprocess)` in
the trace.

---

## Request lifecycle (a tour through one generation)

```
POST /api/generate/jobs    (Authorization: Bearer <jwt>, Idempotency-Key: <uuid>)
   |
   | -- backend/main.py middleware stack:
   |     SecurityHeadersMiddleware
   |     SlowAPIMiddleware  (Redis-backed; required in prod)
   |     JWTAuthMiddleware  -> sets request.state.user (org_id, user_id, cell_id)
   |     UsageGuardMiddleware  -> checks per-org/per-day caps (P0-4 cost cap)
   |     BillingCheckMiddleware -> fail-closed in prod (TD-7 SHIPPED m12-pr11)
   |     IdempotencyMiddleware  -> short-circuits on replay (24h TTL)
   |
   v
backend/app/api/routes/generate/jobs.py  (TD-1: 1500+ lines; planned split)
   - validates input (Pydantic) -> ApplicationBrief
   - persists generation_jobs row (status='queued')
   - enqueues:
       Temporal -> client.start_workflow(GenerationWorkflow, brief, id=job_id)
       OR Redis -> queue.publish('generation.requested', payload)
       OR in-process (gated)
   - returns 202 Accepted + {job_id, sse_url}
   |
   v
GET /api/generate/agentic-stream/{job_id}  (SSE)
   - opens session in AgenticEventEmitter (in-memory; durable replay TODO)
   - emits per-agent events: stage.started, stage.token (if token streaming on),
     stage.completed, pipeline.completed
   - X-Session-ID header for Last-Event-ID resumption
   |
   v   (frontend reads via frontend/src/lib/sseClient.ts -> Mission Control UI)

Behind the scenes, in temporal_worker:

GenerationWorkflow.run(brief)
  for phase in [Recon, Atlas, Cipher, Quill, Forge, Sentinel, Nova]:
    await activity.execute_stage(phase, brief, prev_outputs)
    # each activity:
    #   - reads idempotency token from generation_job_events
    #   - calls ai_engine.api.run_stage(phase, ...)
    #     -> model_router picks provider+model
    #     -> retries (CB 5/60s, retry 6/120s, throttle 100ms)
    #     -> writes one row to ai_invocations (the flight recorder)
    #     -> returns artifact (Pydantic) + telemetry
    #   - persists artifact to document_library / evidence_items
    #   - emits stage.completed via OutboxWriter
    #   - returns; Temporal checkpoints
  emit pipeline.completed
```

The exact stage list is in [AI_CONTEXT.md](AI_CONTEXT.md). The middleware
order is in `backend/main.py` and is **load-bearing** — see
[AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md) for why each layer is
where it is.

---

## Cell architecture (active even with one cell)

From blueprint §5. We have one cell today (`us-east/shard-0`). The protocol
is wired so adding a second cell is a config change.

- A **cell** = `(region, shard)` and owns one Postgres, one Redis, one
  Temporal namespace, one S3 prefix.
- A global `router` Postgres maps `org_id -> cell_id` (3 columns).
- Every JWT carries `cell_id` claim.
- API gateway routes by `cell_id`.
- RLS in each cell scoped to that cell's orgs.
- `CellMigrationWorkflow` is the **only** way to move an org between cells.

Tier-to-cell strategy (blueprint §5.4):

| Tier | Cell |
|---|---|
| Free / Pro | shared `us-east/shard-0` |
| Team | shared `us-east/shard-N` |
| Enterprise | dedicated `us-east/ent-<orgid>` (paid SKU) |
| EU customers | `eu-west/shard-0` (GDPR; Stage B) |

---

## What changes when

The hardest thing about this codebase is **knowing which doc to update when
you change something**. This map is normative.

| If you change… | Update… |
|---|---|
| `backend/app/api/routes/**/*.py` | [API_CONTEXT.md](API_CONTEXT.md), [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md), and any matching `frontend/src/lib/api/` SDK |
| `supabase/migrations/*.sql` | [DATABASE_CONTEXT.md](DATABASE_CONTEXT.md), and run `make schema-snapshot` if it exists |
| `ai_engine/agents/*.py`, `ai_engine/chains/*.py` | [AI_CONTEXT.md](AI_CONTEXT.md) |
| `backend/main.py` middleware | [AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md), [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md), this file |
| `Procfile`, `railway.toml`, `netlify.toml`, `infra/**` | [DEVOPS_INFRA_CONTEXT.md](DEVOPS_INFRA_CONTEXT.md) |
| `config/feature_flags.yaml` | flag is auto-snapshotted by `FeatureFlagAuditService`; document in PR if user-facing |
| `packages/events/schema/v1/*.json` | run codegen `make events-codegen`; update [API_CONTEXT.md](API_CONTEXT.md) §events |
| `docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md` | always update ADR if a decision row changes |
| Anything that introduces a **new failure mode** | add a runbook in `docs/runbooks/` |

The advisory checker `scripts/governance/check_context_freshness.py` will
warn when a watched path moved but the corresponding context file's
`last_synced` did not.

---

## ADR index (decision log)

Live in [`docs/adrs/`](../docs/adrs/). 25 ADRs total today (0001 → 0041,
gaps reserved). Highlights:

- **0001** — Use Supabase for auth + Postgres in Stage A — Accepted
- **0013** — Observability + SRE contract surface — Accepted
- **0030** — Adopt cell architecture protocol now (single cell) — Proposed
- **0031** — Multi-LLM-provider mandatory (Gemini + Anthropic) — Proposed
- **0032** — Per-stage Temporal activities (PR-24 phase 2) — Proposed
- **0033** — Tool registry: capability tokens + sandbox tiers — Proposed
- **0034** — Single migration root (`supabase/migrations/`) — Proposed
- **0035** — Single API entrypoint (`backend/main.py` retired) — Proposed
- **0036** — Realtime gateway extraction trigger — Proposed
- **0037** — `pg_partman` for all partitioned tables — Proposed
- **0038** — JSON Schema validation at OutboxWriter — Proposed
- **0039** — Forbid native EventSource in frontend — Proposed
- **0040** — `import-linter` enforcement of bounded contexts — Proposed

A new "decision-class" change MUST author an ADR before the implementing PR
merges (blueprint §24 PR checklist).

---

## What is **categorically** forbidden

Reproduced from blueprint §17 because new contributors keep reaching for them:

- Direct cross-context imports (caught by `import-linter`).
- Importing `backend.app.*` from `ai_engine/`.
- Adding a new Python entrypoint outside `backend/main.py`.
- Adding a new migration root outside `supabase/migrations/`.
- Adding a tool without a `sandbox_tier` column entry.
- Adding a route without rate limiting (slowapi `@limiter.limit`).
- Returning a model output that has not passed the action gate (no LLM ever
  invokes a tool directly; orchestrator validates against allowlist + token).
- Concatenating user input into a system prompt without `wrap_user_input()`.
- Querying a multi-tenant table without `org_id` in the WHERE clause (RLS
  protects you, but the query plan suffers).
- Bypassing the outbox to fan out a state-changing event.
