# HireStack AI — World-Class Architecture Blueprint

**Status:** Canonical · Authoritative
**Version:** 1.0.0
**Effective:** 2026-05-08
**Owners:** Platform Engineering (architecture WG)
**Supersedes:** `docs/ARCHITECTURE.md` (kept as historical artifact), all root-level `*_PLAN.md`, `*_ROADMAP.md`, `*_MASTERPLAN.md` for architectural decisions

> This document is the **engineering constitution** for HireStack AI.
> Any architectural change — new service, new dependency, new contract,
> new failure mode — **must update this document in the same PR**.
> See [`ENGINEERING_GUARDRAILS.md`](./ENGINEERING_GUARDRAILS.md) §Governance.
>
> Companion documents:
> - [`ENGINEERING_GUARDRAILS.md`](./ENGINEERING_GUARDRAILS.md) — enforced rules
> - [`SCALING_PHASES.md`](./SCALING_PHASES.md) — staged evolution
> - [`PRODUCTION_READINESS_CHECKLIST.md`](./PRODUCTION_READINESS_CHECKLIST.md) — release gates
> - [`ADR_TEMPLATE.md`](./ADR_TEMPLATE.md) — decision-record template

---

## Table of Contents

1. [Architectural Principles](#1-architectural-principles)
2. [Current Architecture (2026-05)](#2-current-architecture-2026-05)
3. [Target Architecture](#3-target-architecture)
4. [Bounded Contexts & Ownership](#4-bounded-contexts--ownership)
5. [Tenancy & Cell Architecture](#5-tenancy--cell-architecture)
6. [AI Runtime Standards](#6-ai-runtime-standards)
7. [Workflow Durability (Temporal)](#7-workflow-durability-temporal)
8. [Event Architecture & Schema Governance](#8-event-architecture--schema-governance)
9. [Realtime Architecture (SSE/WS)](#9-realtime-architecture-ssews)
10. [Data Architecture](#10-data-architecture)
11. [Security Standards](#11-security-standards)
12. [Cost Governance](#12-cost-governance)
13. [Observability Standards](#13-observability-standards)
14. [Deployment & Release Standards](#14-deployment--release-standards)
15. [Reliability, SLOs & Disaster Recovery](#15-reliability-slos--disaster-recovery)
16. [Testing & Quality Standards](#16-testing--quality-standards)
17. [Forbidden Anti-Patterns](#17-forbidden-anti-patterns)
18. [Non-Negotiable Fixes (P0/P1 Register)](#18-non-negotiable-fixes-p0p1-register)
19. [Risk Matrix](#19-risk-matrix)
20. [Technical Debt Register](#20-technical-debt-register)
21. ["Must Never Happen" Failure Scenarios](#21-must-never-happen-failure-scenarios)
22. [Phased Implementation Roadmap](#22-phased-implementation-roadmap)
23. [Architecture Decision Log (ADR Index)](#23-architecture-decision-log-adr-index)
24. [Architecture Impact PR Checklist](#24-architecture-impact-pr-checklist)
25. [Self-Review Notes](#25-self-review-notes)

---

## 1 · Architectural Principles

These five principles govern every architectural decision. When two principles conflict, they are ranked top-to-bottom.

| # | Principle | Implication |
|---|---|---|
| **P1** | **Durability beats throughput.** | At AI cost levels, losing or duplicating a job is worse than running it slowly. Outbox + idempotency are mandatory at every boundary. |
| **P2** | **Contracts beat coordination.** | Every cross-boundary interaction (events, APIs, DB, prompts) is defined by a versioned, machine-checked schema. Drift = CI red. |
| **P3** | **Cells beat clusters.** | Tenant blast radius is bounded by design. Shared infra is a phase, not a destination. |
| **P4** | **Boring infrastructure, opinionated runtime.** | Use proven managed services (Postgres, Redis, Temporal Cloud, Kafka). Spend novelty budget on AI runtime, not on undifferentiated plumbing. |
| **P5** | **Observability is a build-time, not run-time, decision.** | Every event, span, metric, and cost attribution is wired at the moment a code path is written. Retrofitting telemetry is forbidden technical debt. |

**Corollary rules:**

- No new long-running task may be added to a web pod. Web pods accept and dispatch only.
- No new tool may be added to the AI runtime without a JSON Schema + sandbox tier classification.
- No new event type may be emitted without a schema in `packages/events/schema/v1/` and an entry in the registered event list.
- No new database table may be added without RLS enabled and a documented owning context.
- No new external dependency (third-party API, model provider) may be added without an explicit fallback strategy.

---

## 2 · Current Architecture (2026-05)

### 2.1 High-level (as-built)

```
┌──────────────┐   HTTPS    ┌────────────────────────────┐
│ Next.js (Vercel/Netlify)  │  • SSR pages, RSC          │
│ Mobile (Android native)   │  • EventSource SSE         │
└──────┬────────────────────┘                            │
       │ JSON / SSE                                      │
       ▼                                                 │
┌────────────────────────────────────────────────────────┴─┐
│ FastAPI monolith (Railway / Fly.io)                       │
│ • slowapi rate limiting (Redis-backed)                    │
│ • SecurityHeadersMiddleware (raw ASGI, SSE-safe)          │
│ • Supabase JWT verify (RS256/HS256)                       │
│ • usage_guard (per-user 20/day, platform $500/day)        │
│ • check_billing_limit                                     │
│ • Three-tier dispatch:                                    │
│     1. Temporal (ff_temporal_generation)                  │
│     2. Redis Streams (enqueue_generation_job)             │
│     3. In-process asyncio.create_task   ⚠  RISK            │
└──────────┬──────────────────────────┬─────────────────────┘
           │                          │
           ▼                          ▼
   ┌──────────────┐          ┌──────────────────┐
   │ Temporal     │          │ Redis Streams    │
   │ (legacy      │          │ + outbox relay   │
   │  bridge —    │          │ + slowapi store  │
   │  outer       │          │ + cache          │
   │  envelope    │          └──────┬───────────┘
   │  only) ⚠     │                 │
   └──────┬───────┘                 ▼
          │                  ┌──────────────────┐
          ▼                  │ event consumers  │
   ┌──────────────┐          │ (in-process)     │
   │ ai_engine    │          └──────────────────┘
   │ (library)    │
   │ • Gemini only│  ⚠ single provider
   │ • cascade FO │
   │ • breakers   │
   │ • throttle   │
   │ • injection  │
   │   regex      │
   └──────┬───────┘
          ▼
┌────────────────────────────────────────────────────┐
│ Supabase Postgres                                  │
│ • 64/64 tables RLS-enabled  ✅                      │
│ • events_outbox partitioned (3 months seeded) ⚠   │
│ • ai_tool_invocations partitioned ⚠                │
│ • two migration roots (database/ + supabase/) ⚠   │
└────────────────────────────────────────────────────┘
```

### 2.2 What works well today (do not regress)

- **RLS coverage:** 64/64 user-data tables `ENABLE ROW LEVEL SECURITY`.
- **Rate limiting:** 246 `@limiter.limit` decorators across 46/48 route files; per-user keying via JWT `sub`.
- **Per-model circuit breakers** + tenacity retries + quota-aware non-retry classifier in [`ai_engine/client.py`](../../ai_engine/client.py).
- **Outbox writer** with `(org_id, idempotency_key)` UNIQUE + 23505 dedupe.
- **Outbox relay** uses `FOR UPDATE SKIP LOCKED` (multi-replica safe).
- **OTel** + **Langfuse** + **structlog** wired with PII redaction (depth-bounded recursive scrubber).
- **`/metrics`** endpoint auth-gated with `hmac.compare_digest` in production.
- **Tenancy isolation** regression test runs on every PR (separate CI gate).
- **Event schemas v1** (`packages/events/schema/v1/`) with contract test enforcing schema↔registry invariants (PR-26).

### 2.3 Critical weaknesses (current state)

Anchor list referenced throughout the document. Every fix has a tracking entry in §18.

| ID | Weakness | Location |
|---|---|---|
| W1 | Partition rotation is manual (3 months pre-seeded) | [`supabase/migrations/20260521010000_events_outbox.sql`](../../supabase/migrations/20260521010000_events_outbox.sql) |
| W2 | In-process pipeline fallback is unbounded | [`backend/app/api/routes/generate/jobs.py::_start_generation_job_inprocess`](../../backend/app/api/routes/generate/jobs.py) |
| W3 | Queue ACKs unconditionally on handler exception | [`backend/app/core/queue.py::_dispatch`](../../backend/app/core/queue.py) |
| W4 | Single LLM provider (Gemini) | [`ai_engine/client.py`](../../ai_engine/client.py) |
| W5 | Tool registry validator is hand-rolled; no `code_ref` sandbox | [`ai_engine/registry/dispatcher.py`](../../ai_engine/registry/dispatcher.py) |
| W6 | Temporal bridge has no per-stage durability | [`backend/app/temporal/activities/production.py`](../../backend/app/temporal/activities/production.py) |
| W7 | SSE has no `Last-Event-ID` resumption | [`frontend/src/modules/application/hooks/useApplication.ts`](../../frontend/src/modules/application/hooks/useApplication.ts) |
| W8 | No per-org cost cap; cascade can drive 17× spend | [`backend/app/services/usage_guard.py`](../../backend/app/services/usage_guard.py) |
| W9 | Idempotency middleware off by default | `IDEMPOTENCY_ENABLED` env |
| W10 | Two migration roots (`database/` + `supabase/`) | repo root |
| W11 | Two `main.py` files (`backend/main.py` + `backend/app/main.py`) | repo root |
| W12 | Event taxonomy too narrow (5 of ~30 needed) | [`packages/events/schema/v1/`](../../packages/events/schema/v1/) |
| W13 | No staging environment that mirrors production | infra |
| W14 | 9 baseline test failures untracked | CI |
| W15 | Prompt injection defence is regex-only | [`ai_engine/client.py`](../../ai_engine/client.py) |

---

## 3 · Target Architecture

### 3.1 Logical topology (target)

```
                              ┌──────────────────┐
                              │  CDN / WAF       │ Cloudflare
                              └────────┬─────────┘
                                       │
                           ┌───────────┴───────────┐
                           │  api-gateway-svc      │  thin, stateless
                           │  • JWT auth           │  3+ replicas / cell
                           │  • idempotency mw     │
                           │  • rate limit         │
                           │  • request routing    │
                           │  • cell routing       │
                           └─┬────────┬───────┬────┘
                             │        │       │
                ┌────────────┘        │       └──────────────┐
                ▼                     ▼                      ▼
      ┌─────────────────┐   ┌──────────────────┐   ┌────────────────────┐
      │ identity-svc    │   │ billing-svc      │   │ orchestration-svc  │
      │ (read-mostly)   │   │ (cost engine)    │   │ (Temporal client)  │
      └────────┬────────┘   └────────┬─────────┘   └────────┬───────────┘
               │                     │                      │
               └─────────────────────┴──────┬───────────────┘
                                            ▼
                              ┌──────────────────────┐
                              │  Temporal (Cloud)    │
                              │  • GenerationWF      │
                              │  • LongLivedSession  │
                              │  • Cron WFs          │
                              │  • CellMigrationWF   │
                              └──────────┬───────────┘
                                         │
                       ┌─────────────────┴────────────────┐
                       ▼                                   ▼
            ┌────────────────────┐              ┌────────────────────┐
            │ ai-runtime workers │              │ tool-runner sidecar│
            │ • model_router     │◀──── gRPC ───│ • L0/L1/L2 sandbox │
            │ • jsonschema       │              │ • seccomp          │
            │ • trace_llm        │              │ • egress allowlist │
            │ • multi-provider   │              │ • capability tokens│
            └─────────┬──────────┘              └────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 ┌────────────────┐         ┌──────────────────┐
 │ Postgres (cell)│         │ Redis (cell)     │
 │ + pg_partman   │         │ • cache          │
 │ + RLS          │         │ • streams (fanout)│
 │ + outbox       │         │ • pub/sub        │
 └───────┬────────┘         └─────────┬────────┘
         │                            │
         ▼                            ▼
 ┌─────────────────────────────────────────┐
 │ event-relay-svc                          │
 │ • Postgres → Redis Streams + Kafka       │
 │ • FOR UPDATE SKIP LOCKED                 │
 │ • DLQ + replay workflow                  │
 └────────┬───────────────────┬────────────┘
          ▼                   ▼
   ┌────────────┐     ┌──────────────────┐
   │  Kafka     │────▶│ analytics lake   │ (S3 Iceberg)
   │ (managed)  │     │ + ML training    │
   └────────────┘     └──────────────────┘

 Realtime:  realtime-gateway-svc — long-held SSE/WS, fed by Redis pub/sub
 Observability:  OTel → Grafana Cloud + Langfuse (LLM) + Sentry (errors)
 Per-cell:  Postgres, Redis, Temporal namespace, S3 prefix.
```

### 3.2 Tech topology (canonical choices)

| Layer | Stage A (today→10×) | Stage B (10×→100×) | Stage C (100×→1000×) |
|---|---|---|---|
| Hosting | Railway / Fly.io | AWS EKS (per cell) | EKS multi-region |
| DB | Supabase Postgres | Aurora PostgreSQL (per cell) | Aurora multi-region |
| Vector store | pgvector | pgvector + read replicas | Turbopuffer / Qdrant |
| Cache / Streams | Upstash Redis | ElastiCache / Upstash | ElastiCache multi-AZ |
| Event bus | Redis Streams | Redis Streams + Kafka | Redis + Kafka + DLQ archive |
| Workflow | Temporal Cloud | Temporal Cloud (multi namespace) | Temporal multi-region |
| Object storage | Supabase Storage | S3 + cross-region replication | S3 multi-region |
| LLM providers | Gemini + Anthropic | + OpenAI | All three + on-prem fallback (enterprise) |
| Auth | Supabase Auth | Supabase Auth + WorkOS (SSO/SCIM) | WorkOS primary |
| Frontend | Next.js (Vercel) | Next.js + edge functions | Next.js + per-region CDN |
| Mobile | Native Android | + iOS | + Kotlin Multiplatform shared client |
| Observability | Grafana Cloud + Langfuse + Sentry | (same, scaled) | (same, multi-tenant) |
| CI | GitHub Actions | + reusable workflows | + self-hosted runners |

**Choices are sticky.** Replacing any row in this table is an ADR-required change.

---

## 4 · Bounded Contexts & Ownership

The monolith stays one repo. Inside the repo, contexts are **enforced** by package boundaries with `import-linter`.

### 4.1 Context map

| Context | Owns | Code location (today) | Future extraction |
|---|---|---|---|
| **Identity & Tenancy** | users, orgs, RBAC, JWT, RLS policies, cell routing | `backend/app/api/deps.py`, supabase auth | `identity-svc` (Stage B) |
| **Billing & Cost** | plans, budgets, usage counters, cost attribution | `backend/app/services/usage_guard.py`, billing routes | `billing-svc` (Stage B) |
| **Generation Orchestration** | application brief, pipeline, stages, runs | `backend/app/services/pipeline_runtime.py`, `ai_engine/chains/` | `orchestration-svc` (Temporal worker) — Stage A end |
| **AI Runtime** | model routing, retries, breakers, tool dispatch | `ai_engine/` | stays as a library + `tool-runner` sidecar (Stage A) |
| **Knowledge & RAG** | ingestion, vector store, retrieval | `ai_engine/data/` partial | `knowledge-svc` (Stage B) |
| **Realtime** | SSE/WS, presence, pipeline progress | scattered | `realtime-gateway-svc` (Stage A end) |
| **Eventing** | outbox, schemas, relay, DLQ, archival | `backend/app/core/events/`, `packages/events/` | shared library + `event-relay-svc` (Stage A end) |
| **Content Storage** | resumes, JDs, generated docs | Supabase Storage | unchanged + per-region buckets |
| **Public API** | thin HTTP layer | `backend/app/api/routes/` | `api-gateway-svc` (Stage B) |

### 4.2 Enforced import rules

`pyproject.toml` (or `.importlinter`) MUST contain:

```ini
[importlinter]
root_packages = ["backend", "ai_engine"]

[importlinter:contract:1]
name = "ai_engine cannot import from backend.app"
type = forbidden
source_modules = ["ai_engine"]
forbidden_modules = ["backend.app"]

[importlinter:contract:2]
name = "api routes cannot be imported by services"
type = forbidden
source_modules = ["backend.app.services", "backend.app.contexts"]
forbidden_modules = ["backend.app.api.routes"]

[importlinter:contract:3]
name = "contexts are siloed"
type = independence
modules = [
  "backend.app.contexts.identity",
  "backend.app.contexts.billing",
  "backend.app.contexts.orchestration",
  "backend.app.contexts.realtime",
]
```

CI runs `lint-imports` on every PR. Violation = red.

### 4.3 Code ownership (CODEOWNERS)

```
/ai_engine/                @ai-team
/backend/app/contexts/identity/      @platform-team
/backend/app/contexts/billing/       @platform-team
/backend/app/contexts/orchestration/ @platform-team @ai-team
/backend/app/contexts/realtime/      @platform-team
/packages/events/                    @platform-team
/docs/architecture/                  @architecture-wg
/.github/workflows/                  @devex-team
/supabase/migrations/                @platform-team @data-team
```

---

## 5 · Tenancy & Cell Architecture

### 5.1 Cell definition

A **cell** is the tuple `(region, shard)`. Each cell owns:

- One Postgres instance (Aurora / Supabase)
- One Redis instance
- One Temporal namespace
- One S3 bucket prefix
- One set of `event-relay-svc` replicas

### 5.2 Cell routing protocol (mandatory now, even with one cell)

1. Global `router` Postgres holds `org_id → cell_id` mapping (~3 columns; tiny).
2. JWT issued post-login carries `cell_id` claim.
3. Every API request includes JWT; gateway routes to the correct cell deployment.
4. RLS policies in each cell are scoped to orgs in that cell only.

**Why now:** Adding the `cell_id` claim and a router table costs ~2 days. Splitting tenants across cells later becomes a config change rather than a re-architecture.

### 5.3 Cell move

`CellMigrationWorkflow` (Temporal) is the **only** way to move an org between cells:

```
freeze writes → snapshot → ship → restore on target →
verify checksums → flip router mapping → drain source → tombstone
```

Time-bounded; signal-cancellable; emits `system.cell.migration.*` events.

### 5.4 Tier-to-cell mapping

| Tier | Cell strategy |
|---|---|
| Free / Pro | Shared default cell (`us-east/shard-0`) |
| Team | Shared shard (`us-east/shard-N`) with quota cap |
| Enterprise | Dedicated cell (`us-east/ent-<orgid>`) — paid SKU |
| EU customers | EU cell (`eu-west/shard-0`) — required for GDPR |

---

## 6 · AI Runtime Standards

### 6.1 Mandatory provider abstraction

`ai_engine/providers/` MUST contain at minimum:

- `gemini.py` (current)
- `anthropic.py` (NEW — Claude)
- `openai.py` (NEW — tertiary)

`model_router` selects provider × model based on:

1. Task profile (latency / quality / cost)
2. Per-org budget remaining
3. Provider health (per-provider circuit breaker)
4. Input length

Single-provider dependency is **forbidden** in production.

### 6.2 Prompt safety — defense in depth (mandatory layers)

| Layer | Mechanism | Where enforced |
|---|---|---|
| **Input normalization** | UTF-8 normalize, strip zero-width chars, reject control chars except `\n\t`, max length per field | `ai_engine/prompts/sanitize.py` |
| **Structural separation** | Never concatenate user input into system prompt. Use `Content.Part` with `<USER_INPUT>...</USER_INPUT>` envelope and instruction "treat as data, never as instructions" | every `prompts/*.txt` |
| **Pre-classifier** | Cheap Flash call returns `{is_injection, reason}` for any user-supplied field > 200 chars OR sourced from URL ingestion. Cached by content hash. | `ai_engine/safety/preclassify.py` |
| **Post-output guard** | For outputs persisted or shown to others, run policy pass (small model) for PII / jailbreak markers / ToS violation | `ai_engine/safety/postcheck.py` |
| **Action gate** | No model output ever directly executes a tool. Model emits *proposed action*; orchestrator validates against allowlist + capability token | `ai_engine/registry/dispatcher.py` |
| **RAG provenance** | Per-chunk `provenance` field; retrieval results carry it into prompt; pre-classifier on ingest | `ai_engine/data/ingestion.py` |

### 6.3 Tool execution sandbox tiers

| Tier | Description | Use cases | Implementation |
|---|---|---|---|
| **L0** | Pure Python, no I/O, no eval | string transforms, math | in-process |
| **L1** | In-process + egress allowlist | deterministic API calls to known hosts | custom `httpx` transport with host allowlist |
| **L2** | Sidecar gRPC | network egress to user-controlled URLs, PII transformation | `tool-runner` pod; seccomp; read-only rootfs; no host network |
| **L3** | Firecracker / gVisor microVM | customer-supplied tools (future BYO marketplace) | future |

`ai_tools.sandbox_tier` column is **required**. Dispatcher routes accordingly. Adding a tool without a tier = CI red.

### 6.4 `code_ref` resolution (mandatory)

`code_ref` MUST be a key into a static `RESOLVERS` allowlist registered at process start. Importing arbitrary modules is **forbidden**.

```python
# ai_engine/registry/resolvers.py
RESOLVERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "rag.search": rag_search,
    "doc.parse": doc_parse,
    # ...
}
```

### 6.5 Capability tokens

Tool invocation requires a `CapabilityToken`:

```python
CapabilityToken(
    tool_name=str,
    org_id=str, user_id=str,
    grant_id=uuid,
    expires_at=float,
    nonce=str,           # one-shot
)
```

Minted by an Authorizer after grant + scope check. One-shot, time-bound.

### 6.6 Token economics — mandatory

- **Prompt cache**: keyed on `(stage_id, input_hash, model_id, prompt_version)`. Two-tier: in-process LRU + Redis.
- **Prompt versioning**: `prompts/<name>.v<n>.txt` with content hash baked into telemetry.
- **Cost projection**: at request time, estimate tokens × model rate × 1.10 safety margin. Reject if projected cost > remaining org budget.
- **Dynamic model selection**: `model_router` chooses based on input length + task priority + budget remaining.
- **Batch inference** for non-realtime paths (nightly job-fit recompute, etc.).

### 6.7 The AI flight recorder (mandatory table)

```sql
CREATE TABLE ai_invocations (
  id              uuid PRIMARY KEY,
  org_id          uuid NOT NULL,            -- RLS pivot
  workflow_id     text,
  stage_id        text,
  agent_name      text,
  prompt_version  text NOT NULL,            -- content hash
  model_id        text NOT NULL,
  provider        text NOT NULL,            -- gemini | anthropic | openai
  input_hash      bytea NOT NULL,
  output_hash     bytea NOT NULL,
  input_tokens    int NOT NULL,
  output_tokens   int NOT NULL,
  cost_cents      int NOT NULL,
  latency_ms      int NOT NULL,
  cache_hit       bool NOT NULL,
  safety_flags    jsonb NOT NULL DEFAULT '{}',
  langfuse_trace_id text,
  created_at      timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);
```

Every model call writes one row. **No exceptions.** Powers cost dashboards, eval, abuse detection, regulator queries.

---

## 7 · Workflow Durability (Temporal)

### 7.1 Workflow taxonomy

| Workflow | Type | Lifetime | Purpose |
|---|---|---|---|
| `GenerationWorkflow` | one-shot | minutes | one application generation |
| `LongLivedSessionWorkflow` | actor | hours | multi-turn agent session w/ signals |
| `OrgOnboardingWorkflow` | one-shot | days | provisioning, sample data, first-run guidance |
| `PartitionMaintenanceWorkflow` | cron | infinite | DB partition health check |
| `EventArchiveWorkflow` | cron | infinite | monthly outbox → S3 Parquet |
| `DLQReplayWorkflow` | manual | minutes | operator-controlled event replay |
| `CellMigrationWorkflow` | one-shot | hours | move org between cells |
| `BillingReconciliationWorkflow` | cron | minutes | reconcile usage_guard counters with `ai_invocations` |
| `EvalRegressionWorkflow` | cron | hours | nightly gold-set re-run + alert on regression |
| `ChaosWorkflow` | cron | minutes | inject controlled failures (gameday) |
| `DRDrillWorkflow` | quarterly | hours | DR restore + smoke pipeline |

### 7.2 Per-stage activity model (mandatory by Stage A end)

```python
@workflow.defn
class GenerationWorkflow:
    @workflow.run
    async def run(self, input: GenerationInput) -> None:
        await workflow.execute_activity(idempotency_check, input.idempotency_key, ...)
        brief = await workflow.execute_activity(build_brief, input, ...)
        for stage in pipeline.stages:
            output = await workflow.execute_activity(
                execute_stage,
                ExecuteStageInput(stage_id=stage.id, input_hash=hash(stage.input)),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=4,
                    non_retryable_error_types=["UsageGuardExceeded","InvalidInput"],
                ),
            )
            await workflow.execute_activity(persist_stage_output, ...)  # idempotent
            await workflow.execute_activity(emit_event, "generation.stage.completed", ...)
        await workflow.execute_activity(finalize_run, ...)
```

Properties:
- Each `execute_stage` keyed on `(workflow_id, stage_id, input_hash)`. Re-running yields cached result from `stage_results`. **Mid-pipeline crash → resume from last completed stage with zero re-spend.**
- `persist_stage_output` uses outbox pattern → events emitted exactly-once.

### 7.3 Replay safety rules (mandatory)

- No `datetime.now()` inside workflow code → use `workflow.now()`.
- No `random` inside workflow code → use `workflow.random()`.
- No I/O inside workflow code → only inside activities.
- No `asyncio.sleep` → use `workflow.sleep()`.
- All activity inputs/outputs JSON-serializable + JSON-Schema validated at entry.
- Lint with `temporalio` static checker on every PR touching `backend/app/temporal/`.

### 7.4 Versioning

- Backward-compatible change → same workflow version.
- Breaking change → `workflow.patched("v2-stage-merge")`. Old workflows complete under v1; new ones use v2.
- Activity signature changes → add new activity, deprecate old after drain.

### 7.5 Compensation (SAGA)

Every stage activity has paired `compensate_<stage>` activity registered. On unrecoverable failure, workflow walks compensations in reverse: refund usage_guard, void cost record, mark application `generation_failed`, notify user.

### 7.6 Exactly-once

- Idempotency key on every workflow start (`workflow_id = sha256(idempotency_key)`).
- Side effects via outbox pattern only (transactional with workflow intent).
- External non-idempotent calls (Stripe charge, send email) wrapped in `LocalActivity` + per-call idempotency token persisted before call.

---

## 8 · Event Architecture & Schema Governance

### 8.1 Naming convention

`<domain>.<aggregate>.<event_past_tense>` — lowercase, dotted, **immutable once shipped**.

### 8.2 Canonical taxonomy (target v1)

| Domain | Events |
|---|---|
| `identity` | `user.created`, `user.deleted`, `org.created`, `org.deleted`, `org.member.added`, `org.member.removed`, `org.member.role_changed` |
| `billing` | `subscription.activated`, `subscription.cancelled`, `payment.succeeded`, `payment.failed`, `usage.cap.hit`, `budget.warning`, `budget.exceeded` |
| `generation` | `run.started`, `run.completed`, `run.failed`, `stage.started`, `stage.completed`, `stage.failed`, `stage.retried` |
| `ai` | `model.failover`, `model.circuit_opened`, `model.circuit_closed`, `tool.invoked`, `tool.failed`, `safety.flag_raised` |
| `application` | `application.created`, `application.submitted`, `application.matched`, `application.rejected` |
| `system` | `outbox.dead_lettered`, `partition.health_check`, `cell.migration_started`, `cell.migration_completed` |

~30 events. Today there are 5. The 25 missing ones are why audit + ML training + analytics are hard.

### 8.3 Schema evolution rules

- All schemas live in `packages/events/schema/v1/<event>.schema.json`.
- **Adding optional field** → same major version; bump `minor`.
- **Removing or renaming a field** → new major version (`v2/`). v1 kept emitted in parallel for **one full quarter**. Consumers migrate. v1 retired in tracked `event_deprecation` log.
- **Schemas are immutable once shipped.** Old events in storage must remain parseable by their v1 schema forever.

### 8.4 Validation pipeline (mandatory)

`OutboxWriter.append` MUST call `validate_event(event_type, version, payload)` before insert. Validation failure = 500 to caller, no row written. The schema directory is the **enforced** source of truth, not advisory.

### 8.5 Codegen (Stage A end)

`packages/events/codegen` produces:
- Python: Pydantic models in `packages/events/python/`
- TypeScript: zod schemas in `packages/events/ts/`
- Kotlin: Moshi models in `packages/events/kotlin/`

CI runs `pnpm events:codegen --check`. Drift = red.

### 8.6 Streaming topology

```
events_outbox (Postgres, partitioned)
        │
        ▼
event-relay-svc (multi-replica, FOR UPDATE SKIP LOCKED)
        │
        ├─→ Redis Streams events:<type>          (in-house consumers, low latency)
        ├─→ Kafka (managed: Confluent / MSK)     (analytics lake, ML, archival, customer webhooks at Stage B)
        └─→ Webhook dispatcher (per-org webhooks, retries, signing)  [Stage B]
```

Redis = cheap, fast, in-house. Kafka = durable, high-retention, customer-facing.

### 8.7 DLQ + replay

- Per-event-type stream `events:dlq:<type>` after `max_attempts=10`.
- `DLQReplayWorkflow` (Temporal) for operator-controlled replay with filters `(event_type, time_range, org_id)`.
- Operator approval via `signal_with_start`. Audit log written.
- Per-handler `processed_events(consumer_name, event_id)` table enforces idempotency on replay.

---

## 9 · Realtime Architecture (SSE/WS)

### 9.1 Mandatory contract

Every SSE endpoint MUST:

1. Read `Last-Event-ID` request header on connect.
2. Replay missed events from `agent_traces` (or equivalent persistence) starting `event_seq > last_id`.
3. Emit `id: <monotonic_seq>` line on every event.
4. Send `:keepalive` comment every 15s to defeat proxy timeouts.
5. Set `Cache-Control: no-store` and `X-Accel-Buffering: no`.

### 9.2 Frontend rule

Native `EventSource` is **forbidden** for any new code. Use `@microsoft/fetch-event-source` (supports `Authorization: Bearer …` headers and built-in reconnect with last-event-id memory). Migrate existing usage in [`useApplication.ts`](../../frontend/src/modules/application/hooks/useApplication.ts).

### 9.3 Realtime gateway extraction (Stage A end)

When SSE connections > 1000 concurrent OR rolling deploys cause user-visible disconnects:

- Extract `realtime-gateway-svc`.
- Web pods publish to Redis pub/sub.
- Gateway pods fan out to clients.
- Web pods become short-request only — OK for rolling restarts.

### 9.4 Mobile / enterprise WebSocket fallback

WebSocket fallback for clients where `text/event-stream` is blocked by corporate proxies (common in enterprise networks). Same event contract; different transport.

---

## 10 · Data Architecture

### 10.1 Single migration root

**Achieved (m9-pr33, M10):** `supabase/migrations/` is the **sole** source of truth. The legacy `database/migrations/` directory and the `database/` aggregated SQL bundles (`apply_*.sql`, `combined_migration.sql`, `hirestack_full_migration.sql`) have been deleted. `backend/tests/unit/test_supabase_migrations_mirror.py::test_legacy_database_migrations_dir_does_not_exist` blocks resurrection.

### 10.2 Migration discipline

- Every migration is **expand → migrate → contract**: never rename/drop in one step.
- Any DDL on a > 1M row table must use `CREATE INDEX CONCURRENTLY`, batched updates, or `pg_repack` patterns.
- A migration safety linter runs in CI checking for unsafe operations on hot tables.
- Every migration that adds a partitioned table also adds the partition to `pg_partman` config in the same file.

### 10.3 Partition management

- **Tool:** `pg_partman` extension.
- **Config:** `premake = 6`, `retention = 24 months` for `events_outbox` and `ai_tool_invocations`. `retention = 84 months` for `ai_invocations` (compliance).
- **Maintenance:** `pg_cron` nightly: `SELECT partman.run_maintenance_proc();`.
- **Verification:** `PartitionMaintenanceWorkflow` (Temporal cron) asserts next-month partition exists for every partitioned table; pages on miss with **14-day lead time**.
- **Archival:** Detached partitions → S3 Parquet via `EventArchiveWorkflow`. Cold queries hit lake; hot queries hit Postgres.

### 10.4 RLS policy

- **100% RLS coverage on user-data tables. Enforced by CI test.**
- New table without RLS = CI red.
- Service-role-only tables (outbox, audit_log) carry an explicit `service_role_only` policy.

### 10.5 Backups

- Postgres: PITR + daily logical backups to S3 (cross-region replicated).
- Object storage: S3 cross-region replication.
- Quarterly DR drill restores backup → sandbox cell → smoke pipeline.

### 10.6 Vector store evolution

- **Stage A:** pgvector. ~10M vectors max.
- **Stage B:** Migrate to Turbopuffer (cost-efficient) or Qdrant (self-hosted control). Migration is a single Temporal workflow.
- Vector schema versioned alongside event schemas.

---

## 11 · Security Standards

### 11.1 Auth

- Supabase JWT (RS256 in prod, HS256 fallback for legacy). `JWT_SECRET` required in prod (validator enforced).
- Stage B: WorkOS for SSO/SCIM at enterprise tier.
- All routes enforce auth via `Depends(get_current_user)` unless explicitly public (`health.py` only).

### 11.2 Authorization

- RLS on every user-data table.
- Tenancy isolation regression test required green on every PR.
- Capability tokens for tool invocation (§6.5).
- Admin actions write to `audit_log` table (Stage A end).

### 11.3 Network

- All inbound via Cloudflare WAF.
- TLS 1.3 only.
- HSTS preload.
- CSP `default-src 'self'` (already enforced by `SecurityHeadersMiddleware`).

### 11.4 Secrets

- No secrets in source. Enforced by CI grep gate.
- Env via Railway/Vercel secret stores; Stage B: AWS Secrets Manager.
- No secrets in logs (PII redactor scrubs ~17 key patterns; depth bounded; audited monthly).
- JWT verification key rotated quarterly.

### 11.5 Rate limiting

- `slowapi` per-user via JWT `sub` (already in place).
- Redis backend **required in production** — startup check fails if Redis unreachable. In-memory fallback is forbidden in prod.
- Coverage: every route file (CI gate enforces).

### 11.6 Prompt injection / AI safety

See §6.2. Defense in depth is **mandatory**, not optional.

### 11.7 Compliance roadmap

| Standard | Stage | Owner |
|---|---|---|
| SOC 2 Type I | Stage A end | platform |
| SOC 2 Type II | Stage B mid | platform |
| ISO 27001 | Stage B end | platform |
| GDPR (EU cell) | Stage B start | platform |
| HIPAA | only if customer paid | future |
| EU AI Act | Stage B (audit log + risk classification) | architecture-wg |

---

## 12 · Cost Governance

### 12.1 Three-tier caps (mandatory)

| Layer | Limit source | Action on hit |
|---|---|---|
| Per-user daily generations | env (default 20) | 429, retry next UTC day |
| Per-org daily $ cap | `org_billing.daily_budget_cents` | 402, payload includes `payment_required`; Slack to org admin webhook |
| Per-task model promotion gate | sliding window (5 min) | If Flash error rate > 20%, stop cascading to Pro for that task; fail request; page SRE |
| Platform $ cap | env (default $500) | Emergency brake; pause non-paid traffic; page CTO |

### 12.2 Cost attribution (mandatory by Stage A end)

`ai_invocations.cost_cents` is the source of truth. A Postgres materialized view `org_cost_hourly` aggregates by `(org_id, hour)`. Refresh: `pg_cron` every 60s.

### 12.3 Pre-flight cost projection

Before dispatch, estimate cost as `tokens × model_rate × 1.10`. Reject (402) if projected > remaining org budget.

### 12.4 Per-pipeline cost budget

Every pipeline definition carries `expected_cost_cents`. CI gate fails if a new pipeline's projection > 1.5× the median.

### 12.5 Reporting

- Per-customer cost dashboard (Grafana).
- Weekly cost review (Friday standing).
- Monthly board metric: cost per generation, gross margin per tier.

---

## 13 · Observability Standards

### 13.1 Three pillars + LLM

| Pillar | Tool | Owner |
|---|---|---|
| Metrics | Prometheus → Grafana Cloud | SRE |
| Traces | OTel → Tempo or Honeycomb | SRE |
| Logs | structlog → Loki | SRE |
| LLM | Langfuse | AI team |
| Errors | Sentry | All |

### 13.2 Mandatory instrumentation

Every code path that:

- **Issues an HTTP request** → wrapped in OTel span (auto via `HTTPXClientInstrumentor`).
- **Calls an LLM** → wrapped in `trace_llm` (Langfuse) AND writes `ai_invocations` row.
- **Emits an event** → uses `OutboxWriter.append` (which traces).
- **Holds a long connection (SSE/WS)** → emits `realtime.connection_*` metrics.
- **Crosses a cell boundary** → carries `trace_id` via `traceparent` header.

### 13.3 The four golden SLOs

| SLO | Target | Measurement |
|---|---|---|
| Generation success rate | ≥ 99.5% | `generation.run.completed / generation.run.started` over 7d |
| Generation p95 latency | ≤ 90s | from `run.started` to `run.completed` |
| API availability (non-generation) | ≥ 99.95% | external prober every 30s |
| LLM cost per generation (median) | ≤ budgeted | `ai_invocations.cost_cents` median |

Each SLO has a multi-window burn-rate alert (fast 1h, slow 6h). Page on fast burn; ticket on slow burn.

### 13.4 Single pane of glass

Grafana dashboards link `trace_id` to logs (Loki), traces (Tempo), Langfuse spans, and Sentry errors. **One click from Sentry error to offending workflow + LLM call.**

### 13.5 `/metrics` migration

Hand-rolled `/metrics` endpoint in [`backend/main.py`](../../backend/main.py) is **legacy**. Migrate to `prometheus_client` at Stage A end. Auth gate stays.

---

## 14 · Deployment & Release Standards

### 14.1 Branching & PRs

- Trunk-based + short-lived PR branches.
- Stacked PRs encouraged (`pr-N` chain). One concern per PR.
- PR title prefix: `[<context>] <verb> <noun>`. Example: `[orchestration] split run_pipeline into per-stage activities`.
- Required reviews: 1 for context-local change, 2 for cross-context, 1 architecture-wg member for any blueprint update.

### 14.2 PR-required CI gates

| Gate | Blocking | Owner |
|---|---|---|
| Lint (ruff, eslint) | yes | devex |
| Typecheck (mypy if installed, tsc) | yes | devex |
| Unit tests | yes | all |
| Integration tests (testcontainers) | yes | all |
| Contract tests (event schemas) | yes | platform |
| Tenancy isolation | yes | security |
| Eval gate (when prompts changed) | yes | ai-team |
| Security scan (secrets) | yes | security |
| `import-linter` contracts | yes | architecture-wg |
| Coverage ≥ 70% on changed packages | yes (Stage A end) | devex |
| Migration safety linter | yes | data-team |
| Dependency CVE scan | advisory now → yes (Stage B) | security |

PR feedback budget: **≤ 5 min unit, ≤ 10 min full.** Use `pytest-xdist`, npm cache.

### 14.3 Deploy pipeline

```
PR merge → main → CI green
  → preview deploy (auto)
  → manual approval (prod)
  → canary 5% (5 min, SLO watch)
  → canary 25% (10 min, SLO watch)
  → 100%
  → smoke test
  → on SLO burn → AUTO ROLLBACK
```

Required preview environment per PR for any DB migration or contract change.

### 14.4 Feature flags

- All new behavior behind `ff_<name>` flag, defaulted **off**.
- Flag has DRI + sunset date in metadata.
- Flag flips **audited** to `audit_log` table.
- Flags stored centrally (env now → `feature_flags` table at Stage A end).
- A flag without an owner OR past sunset date is removed by a quarterly cleanup workflow.

### 14.5 Migration safety

- Expand → migrate → contract.
- No drop / rename in single step.
- Unsafe ops on hot tables blocked by linter.
- Backfill scripts idempotent + resumable.
- Migration test runs against a copy of prod schema in CI.

---

## 15 · Reliability, SLOs & Disaster Recovery

### 15.1 SLO targets (see §13.3)

### 15.2 Error budgets

Each SLO carries an error budget (1 - SLO target). Budget burn > 50% in a quarter triggers a **feature freeze** on the affected context until budget is restored. Non-negotiable.

### 15.3 Disaster Recovery RPO/RTO

| Tier | RPO | RTO | Mechanism |
|---|---|---|---|
| Postgres | 5 min | 1 hour | PITR + daily logical backups to S3 |
| Redis | best-effort | 15 min | Rebuilt from outbox replay |
| Object storage | 0 | minutes | S3 cross-region replication |
| Temporal | 0 | minutes | Temporal Cloud multi-region OR self-hosted Cassandra mirroring |

Quarterly `DRDrillWorkflow` proves these numbers. **A drill that fails is a P0.**

### 15.4 Chaos engineering

`ChaosWorkflow` (weekly, non-prod):

- Kills random pod
- Blackholes Redis 90s
- Returns 500 from random Gemini call
- Forces Temporal worker restart
- Injects 10× latency on Postgres

Asserts SLO unaffected. Failure = ticket.

### 15.5 Incident response

- PagerDuty rotation; runbook URL in alert payload.
- Status page (Statuspage) auto-updated from `system.*` events.
- Blameless postmortem for every Sev1/Sev2; published to `docs/postmortems/`; action items tracked with SLAs.

---

## 16 · Testing & Quality Standards

### 16.1 Pyramid

| Layer | Coverage target | Owner |
|---|---|---|
| Unit | ≥ 70% on `ai_engine/`, `backend/app/contexts/` | code author |
| Contract | one per service boundary; one per event schema | context owner |
| Integration | testcontainers (Postgres, Redis, Temporal); every PR | code author |
| E2E (Playwright) | critical user flows; nightly + on staging deploy | qa team |
| Eval (gold corpus) | every prompt change + nightly | ai-team |
| Chaos | weekly on non-prod | SRE |
| Load (k6) | weekly; results dashboarded | SRE |

### 16.2 Mutation testing (Stage A end)

`mutmut` on `ai_engine/safety/` and `backend/app/contexts/billing/`. Critical paths must score ≥ 80%.

### 16.3 Fuzz testing

`hypothesis` against:
- Prompt injection sanitizer (§6.2)
- Event schema validator
- JWT parser

### 16.4 Speed budget

PR feedback ≤ 5 min unit, ≤ 10 min full. Slow tests live in a separate `slow/` directory and run nightly.

---

## 17 · Forbidden Anti-Patterns

The following are **forbidden in production code** as of v1.0.0. CI will be configured to fail on each.

| # | Anti-pattern | Why |
|---|---|---|
| AP-1 | Long-running task in web pod (`asyncio.create_task` for > 5s work) | Kills p99 under burst; OOMs the pod |
| AP-2 | New `EventSource` (native) in frontend code | No reconnect, no header support |
| AP-3 | Concatenating user input into LLM system prompt | Injection vector |
| AP-4 | Tool registry `code_ref` pointing outside `RESOLVERS` allowlist | Arbitrary code execution |
| AP-5 | Emitting an event without a registered schema | Contract drift |
| AP-6 | DB migration with rename/drop in single step | Production-breaking |
| AP-7 | New table without RLS | Tenancy escape |
| AP-8 | `datetime.now()` inside Temporal workflow code | Replay non-determinism |
| AP-9 | Single-LLM-provider dispatch in production | Outage on Gemini quota event |
| AP-10 | Hardcoded secret in source | Compliance + leak risk |
| AP-11 | `slowapi` in-memory fallback in production | Multi-instance budget escape |
| AP-12 | New cross-context import without architecture-wg review | Boundary erosion |
| AP-13 | New external dependency without fallback strategy | Single point of failure |
| AP-14 | New ADR-worthy decision without ADR | Drift |
| AP-15 | Free-text prose at internal LLM stage boundary (no structured output) | Brittle pipelines |
| AP-16 | Idempotency middleware off in production | Double-charge risk |
| AP-17 | Queue ACK before handler success | Silent job loss |
| AP-18 | Partition table without `pg_partman` registration | 90-day fuse to outage |

---

## 18 · Non-Negotiable Fixes (P0/P1 Register)

Every fix has a tracking ID. Status updated in PRs. Closing the last entry in this section is the **gate to declare "Stage A complete."**

> **Status legend** — SHIPPED = merged on the m6→m12 branch chain (not yet on `main`).
> Status reconciled in m12-pr04 against actual code. See repo memory for per-PR notes.

### P0 — Production-outage class (must ship within next milestone)

| ID | Title | Refs | Owner | Status |
|---|---|---|---|---|
| P0-1 | Partition rotation: `pg_partman` + `PartitionMaintenanceWorkflow` | W1 | platform | **SHIPPED** — m7-pr27a (`supabase/migrations/20260508120000_outbox_partition_rotation.sql`) |
| P0-2 | Eliminate in-process generation fallback; fail-fast 503 | W2 | platform | **SHIPPED** — m7-pr27b |
| P0-3 | Queue ACK on success only; DLQ + idempotent handlers | W3 | platform | **SHIPPED** — m7-pr27c |
| P0-4 | Per-org daily $ cap + cascade-failure breaker | W8 | platform | TODO |
| P0-5 | Tool registry: `jsonschema` + capability tokens + sandbox tiers | W5 | ai-team + security | **SHIPPED** — m7-pr29 |
| P0-6 | Idempotency middleware ON in production | W9 | platform | **SHIPPED** — `backend/main.py` middleware stack |
| P0-7 | SSE `Last-Event-ID` resumption end-to-end | W7 | frontend + platform | **SHIPPED** (m12-pr05) — backend exposes `GET /pipeline/agentic-stream/{session_id}/replay?after_sequence=N` backed by `AgenticEventEmitter.get_events_after()`; `agentic_stream.py` returns `X-Session-ID` header so clients can resume; in-memory store is single-process — durable cross-pod replay still requires Redis/DB-backed session registry (tracked separately) |

### P1 — SLO-impacting / data-loss class (must ship within Stage A)

| ID | Title | Refs | Owner | Status |
|---|---|---|---|---|
| P1-1 | Phase-2 Temporal: per-stage activities + idempotent persist | W6 | platform | **SHIPPED** — m8-pr32 (`backend/app/temporal/activities/__init__.py`) |
| P1-2 | Strict event-payload validation at `OutboxWriter.append` | W12 | platform | **SHIPPED** — m7-pr31 |
| P1-3 | Add ~25 missing canonical event types + schemas | W12 | all | **SHIPPED** — m6-pr26 |
| P1-4 | Second LLM provider (Anthropic Claude) integrated behind `model_router` | W4 | ai-team | **SHIPPED** — m7-pr28 |
| P1-5 | Single migration root (consolidate `database/` into `supabase/`) | W10 | data-team | **SHIPPED** — `database/` removed |
| P1-6 | Single `main.py` entrypoint | W11 | platform | **SHIPPED** — only `backend/main.py` remains |
| P1-7 | Real codegen (Python/TS/Kotlin) from `packages/events/schema/v1/` | — | platform | **SHIPPED** — `packages/events/scripts/codegen.py` + `Makefile` targets |
| P1-8 | Per-customer cost attribution table + materialized view | — | platform | TODO |
| P1-9 | Centralized feature-flag service with audit | — | platform | **PARTIAL** — `config/feature_flags.yaml` + sunset-CI live; audit table pending |
| P1-10 | Coverage gate + xdist in CI; promote `deps-audit` to required | — | devex | **SHIPPED** — coverage gate (m12-pr02), xdist + `deps-audit` required (m12-pr04) |
| P1-11 | Triage 9 baseline test failures (fix or `xfail` with linked issues) | W14 | all | SHIPPED (m12-pr06) — 7 stale tests pointing at moved/renamed code; 4090/4090 green |
| P1-12 | Adversarial prompt-injection defense (pre-classifier + structural separation) | W15 | ai-team + security | TODO |
| P1-13 | Realtime gateway extraction (when SSE > 1000 concurrent) | — | platform | DEFERRED — gates on SSE > 1000 concurrent |
| P1-14 | `import-linter` contracts wired in CI | — | architecture-wg | **SHIPPED** — `.github/workflows/architecture.yml` |
| P1-15 | Staging environment that mirrors production (per-PR previews + shared staging) | W13 | devex | **SHIPPED** — m11-pr45 (`infra/staging-mirror.compose.yml`) |

---

## 19 · Risk Matrix

Likelihood × Impact (each scored 1–5). Score ≥ 12 requires active mitigation.

| Risk | Likelihood | Impact | Score | Mitigation | Owner |
|---|---|---|---|---|---|
| Gemini quota / regional outage | 4 | 5 | **20** | P1-4 (multi-provider) | ai-team |
| Partition expiry → outbox writer dies | 5 | 5 | **25** | P0-1 (partman) | platform |
| In-process fallback OOM under Redis outage | 3 | 5 | **15** | P0-2 (fail-fast) | platform |
| Silent job loss via queue ACK | 4 | 4 | **16** | P0-3 (ACK on success) | platform |
| Cost runaway (cascade promotion under bad release) | 3 | 5 | **15** | P0-4 (per-org cap + breaker) | platform |
| Tool registry abuse via `code_ref` | 2 | 5 | 10 | P0-5 (allowlist + sandbox) | security |
| Compliance audit failure (no audit log) | 3 | 4 | 12 | Stage B audit_log table | platform |
| Single cell hits DB scaling ceiling | 2 | 5 | 10 | Stage B cell sharding | platform |
| Schema drift between Python/TS/Kotlin | 4 | 3 | 12 | P1-7 (codegen) | platform |
| Long-held SSE breaks rolling deploys | 4 | 3 | 12 | P1-13 (realtime gateway) | platform |
| Prompt-injection successful exfiltration | 3 | 5 | 15 | P1-12 (defense in depth) | ai-team + security |
| 9 baseline test failures hide regressions | 4 | 3 | 12 | P1-11 (triage) | all |

---

## 20 · Technical Debt Register

Items that are not P0/P1 but must be tracked. Reviewed quarterly.

| ID | Item | Why it matters | Trigger to fix |
|---|---|---|---|
| TD-1 | `generate/jobs.py` is 1500+ lines | Merge conflicts at scale | Next major change in that file |
| TD-2 | Sentry redaction depth bound = 8 | Deep AI objects can leak at depth 9+ | Increase to 16 or convert to iterative |
| TD-3 | Hand-rolled `/metrics` text format | Two metric paths to maintain | Stage A end |
| TD-4 | `requirements.txt` unpinned ranges | Reproducibility | Add `requirements.lock` (pip-compile) |
| TD-5 | Python 3.11 in CI vs 3.13 local | Dev/CI drift | Pin one and document |
| TD-6 | Multiple root-level `*_PLAN.md` | No canonical doc → drift | Archive to `docs/_archive/` (this PR) |
| TD-7 | `_billing_logger` swallows org-fetch errors | Fail-open on Supabase outage | Make fail-closed in prod |
| TD-8 | No mutation testing | Critical paths under-tested | Stage A end |
| TD-9 | No per-region observability sharding | One Sentry org = noise | Stage C |
| TD-10 | Dual-namespace lazy imports in `ai_engine/client.py` | Smell of unsettled package layout | Resolved by P1-6 |

---

## 21 · "Must Never Happen" Failure Scenarios

These scenarios are **categorically unacceptable**. Each has a tested guarantee preventing it.

| Scenario | Guarantee | Tested by |
|---|---|---|
| User A reads User B's data | RLS on every user-data table | `tests/security/test_tenancy_isolation.py` |
| AI cost incident exceeds platform cap | `usage_guard` hard ceiling + per-org cap | `tests/test_usage_guard_*.py` |
| Mid-pipeline crash re-burns tokens | Per-stage activity + idempotent persist (P1-1) | future `tests/temporal/test_resume.py` |
| Job silently disappears | DLQ + idempotent handler enforcement (P0-3) | future `tests/queue/test_dlq.py` |
| Partition expires without warning | `pg_partman` + 14-day verifier alert (P0-1) | future `tests/db/test_partition_health.py` |
| Adversarial input executes a tool | Action gate + capability token (§6.4–6.5) | future `tests/ai/test_action_gate.py` |
| Hardcoded secret reaches main | CI secret scanner | `.github/workflows/ci.yml` |
| Schema drift between producers and consumers | Contract test on every PR | `backend/tests/contracts/test_event_schema_contract.py` |
| Migration with rename/drop in one step ships | Migration safety linter | future CI gate |
| Single Gemini outage takes down platform | Multi-provider model_router (P1-4) | future `tests/ai/test_provider_failover.py` |

---

## 22 · Phased Implementation Roadmap

See [`SCALING_PHASES.md`](./SCALING_PHASES.md) for full detail.

### Stage A — Today → 10× (~50K generations/day)
- All P0 fixes (P0-1 through P0-7).
- Phase-2 Temporal (P1-1).
- Per-customer cost attribution (P1-8).
- Multi-provider AI (P1-4).
- Single migration root + single main.py (P1-5, P1-6).
- `import-linter` enforcement (P1-14).
- SSE resumption (P0-7).

**Exit criteria:** All P0 closed. SLO instrumentation live. DR drill green.

### Stage B — 10× → 100× (~5M generations/day)
- Cell architecture (multi-cell, single region).
- Realtime gateway extracted.
- Kafka added as parallel event bus.
- Knowledge-svc extracted.
- Identity-svc extracted.
- Read replicas for Postgres.
- WorkOS SSO/SCIM.
- Audit log table.
- SOC 2 Type II evidence collection.

**Exit criteria:** First enterprise customer on dedicated cell. EU cell live.

### Stage C — 100× → 1000× (hyperscale, multi-region)
- Active-active cells per region.
- Vector store migrated off pgvector.
- Cold storage tier (Iceberg on S3).
- pgBouncer per cell.
- Per-region observability.

**Exit criteria:** $50M+ ARR; multi-region paid customers.

### Anti-overengineering rules
- Do **not** shard Postgres before Stage B.
- Do **not** introduce Kafka before Stage B.
- Do **not** go multi-cloud until a customer pays for it.
- Do **not** build control-plane / dataplane split before Stage C.

---

## 23 · Architecture Decision Log (ADR Index)

ADRs live in [`docs/adrs/`](../adrs/). Use [`ADR_TEMPLATE.md`](./ADR_TEMPLATE.md). Numbering is sequential.

| # | Title | Date | Status |
|---|---|---|---|
| 0001 | Use Supabase for auth + Postgres in Stage A | 2025-XX | Accepted |
| 0013 | Observability + SRE contract surface | 2026-04 | Accepted |
| ... | (existing ADRs) | | |
| **0030** | **Adopt cell architecture protocol now (single cell)** | TBD | **Proposed** |
| **0031** | **Multi-LLM-provider mandatory (Gemini + Anthropic)** | TBD | **Proposed** |
| **0032** | **Per-stage Temporal activities (PR-24 phase 2)** | TBD | **Proposed** |
| **0033** | **Tool registry: capability tokens + sandbox tiers** | TBD | **Proposed** |
| **0034** | **Single migration root (`supabase/migrations/`)** | TBD | **Proposed** |
| **0035** | **Single API entrypoint (`backend/main.py` retired)** | TBD | **Proposed** |
| **0036** | **Realtime gateway extraction trigger** | TBD | **Proposed** |
| **0037** | **`pg_partman` for all partitioned tables** | TBD | **Proposed** |
| **0038** | **JSON Schema validation at OutboxWriter** | TBD | **Proposed** |
| **0039** | **Forbid native EventSource in frontend** | TBD | **Proposed** |
| **0040** | **`import-linter` enforcement of bounded contexts** | TBD | **Proposed** |

Each Proposed ADR must be authored before the corresponding implementation PR.

---

## 24 · Architecture Impact PR Checklist

Every PR that touches one or more of:

- `ai_engine/`
- `backend/app/contexts/`
- `backend/app/temporal/`
- `backend/app/core/{events,queue,security}.py`
- `packages/events/`
- `supabase/migrations/`
- `docs/architecture/`

MUST include this checklist in the PR description (failing items block merge):

```markdown
## Architecture Impact

- [ ] **Bounded context**: This change is contained within ___ context.
- [ ] **Cross-context interactions**: List all imports/calls across context boundaries: ___
- [ ] **Contract impact**: Lists any new/changed event types, API endpoints, DB tables, prompt versions: ___
- [ ] **Schema versioning**: Backward-compatible? If breaking, ADR linked: ___
- [ ] **Forbidden anti-patterns**: Confirmed none of §17 violated.
- [ ] **Observability**: New code path emits metric/trace/log/event as required by §13.2.
- [ ] **Cost impact**: New LLM calls projected and accounted in cost cap (§12).
- [ ] **Security**: RLS + auth + capability checks where applicable (§11).
- [ ] **Tests**: Unit + integration + (if applicable) contract + chaos.
- [ ] **Blueprint update**: If this changes architecture, the blueprint section ___ is updated in this PR.
- [ ] **ADR**: If decision-class change, ADR ___ is added/updated in this PR.
- [ ] **Runbook**: If new failure mode, runbook updated.
```

PRs without this section, or with unchecked items, are **automatically blocked**.

---

## 25 · Self-Review Notes

Internal contradictions, weak assumptions, and unresolved risks identified during authoring. Tracked here so future readers know the open questions.

### 25.1 Contradictions resolved

- **Stage A says "stay on Supabase"; Stage B says "Aurora."** Resolution: Supabase Postgres → migrate to Aurora at cell-sharding time. Same SQL surface; documented as ADR-TBD.
- **§6.2 mandates pre-classifier; §16.1 wants ≤5min PR feedback.** Resolution: pre-classifier runs in async path, not in CI. CI tests the classifier API contract only.
- **§7.5 SAGA compensation vs §12.1 fail-fast 402.** Resolution: 402 happens *before* dispatch. Compensation only fires on errors during/after stage execution.

### 25.2 Weak assumptions (flagged for review)

- **Cell-router lookup latency.** Assumed < 5ms. Validate when implementing.
- **`pg_partman` Supabase support.** Confirmed available; verify version compatibility before P0-1 implementation.
- **Anthropic API parity with Gemini for our pipelines.** Eval gate must run against both before declaring P1-4 complete.
- **Temporal Cloud SLA vs cost.** At Stage B end, evaluate self-hosted Temporal cost-benefit.
- **Customer appetite for dedicated cells.** Pricing experiment needed before investing in CellMigrationWorkflow polish.

### 25.3 Operational blind spots (acknowledged)

- **No real chaos engineering today.** Mitigation: ChaosWorkflow is in §15.4 but not yet built. Tracked separately.
- **No pricing telemetry on tool invocations.** Mitigation: `ai_invocations` table covers AI; `ai_tool_invocations` covers tools; need a unified dashboard.
- **Frontend bundle size not budgeted.** Add a Lighthouse CI gate in Stage A end.
- **No on-call rotation defined yet.** Single founder/eng currently. Add as soon as 2nd engineer joins.

### 25.4 Unresolved risks

- **Gemini API contract changes.** No SLA from Google on prompt format. Mitigation: provider abstraction (P1-4) + integration tests against each provider weekly.
- **Browser proxies blocking SSE in enterprise.** Mitigation: WebSocket fallback (§9.4) — not yet specified in detail.
- **Vector store migration cost.** Stage B item, but volume could surprise. Add per-month "vectors stored" metric to dashboard.

### 25.5 Areas vulnerable to future drift

- **Prompt files** (`ai_engine/prompts/`) — content easy to change without version bump. Mitigate: prompt content hash in CI (Stage A end).
- **Feature flags** — easy to add, hard to remove. Mitigate: quarterly cleanup workflow + sunset date in metadata.
- **Event types** — easy to add to schema dir without registering. Mitigate: contract test (already in place).
- **DB tables without RLS** — easy to forget. Mitigate: CI test (already in place; reinforced by CODEOWNERS).
- **Cross-context imports** — easy to slip in. Mitigate: `import-linter` (P1-14).

---

## End of Blueprint

This document is versioned. Material changes require:

1. PR with diff to this file.
2. Architecture-WG review.
3. Updated ADR index.
4. Version bump at top of file.

Last review date: **2026-05-08**
Next mandatory review: **2026-08-08** (quarterly)
