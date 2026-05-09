---
title: File Tree (annotated)
last_synced: 2026-05-08
watch_paths:
  - "*"
  - ai_engine
  - backend
  - frontend
  - supabase
  - packages
  - infra
  - scripts
  - docs
canonical_sources:
  - README.md
update_when:
  - a new top-level folder is added
  - a top-level deployable is renamed (frontend, backend, mobile)
  - a major subfolder is restructured (e.g. ai_engine/agents/<new-domain>/)
  - tests directory layout changes
---

# File Tree (annotated)

> Authoritative map of the repository. Each entry has one line of intent —
> "what lives here and why." When a folder no longer matches its intent,
> either move the code or update this file.
>
> The full tree is too large to dump. This is the **navigated** view: the
> directories an engineer needs to recognize at a glance, plus the files
> that are load-bearing. Anything not listed is either a leaf (test file,
> migration, single-purpose module) or generated.

---

## Top-level (repo root)

```
HireStack AI/
├── README.md                 — project intro, run commands, agent names
├── CHANGELOG.md              — release notes; updated on every shipping PR
├── CONTRIBUTING.md           — dev workflow + context system maintenance section
├── LICENSE
├── SECURITY.md               — vulnerability disclosure
├── RELEASE.md                — release runbook
├── MODULARIZATION_PROGRESS.md — running notes on bounded-context extraction
├── pyproject.toml            — Python packaging + import-linter contracts
├── mypy.ini                  — type-check config
├── conftest.py               — repo-root pytest hooks
├── requirements.txt          — convenience top-level (see backend/ for canonical)
├── Procfile                  — declares Railway processes: api / worker / scheduler / temporal_worker
├── railway.toml              — Railway deployment config
├── netlify.toml              — Netlify deployment config
├── Makefile                  — common dev targets
├── ai_engine/                — AI runtime library (library-only; no backend imports)
├── backend/                  — FastAPI app + tests + Dockerfile
├── frontend/                 — Next.js 14 app + tests + e2e + Dockerfile
├── mobile/                   — Native Android (lib/ shared) + sideload notes
├── supabase/                 — single migration root + seed.sql + config.toml
├── packages/                 — shared schemas (events/) — produces TS / Py / Kotlin
├── infra/                    — docker-compose + observability + staging mirror
├── config/                   — feature_flags.yaml + other static config
├── docs/                     — architecture, ADRs, runbooks, journal, _archive
├── reference/                — read-only reference material (career-ops/)
├── scripts/                  — ops, governance, dev, and one-off scripts
├── tools/                    — codegen, codemods (build-time helpers)
├── k6/                       — load test scenarios + flows
├── output/                   — generated artifacts (gitignored runtime output)
└── supabase/migrations/      — see Database section below
```

---

## `ai_engine/` — AI runtime library

**Boundary rule (blueprint §4.2):** `ai_engine` MAY NOT import from
`backend.app`. The only public surface is [`ai_engine/api.py`](../ai_engine/api.py).
Enforced by `import-linter` contract #1.

```
ai_engine/
├── __init__.py               — package marker
├── api.py                    — PUBLIC SURFACE: run_stage, run_chain, run_pipeline
├── client.py                 — LLM client wrapper (CB 5/60s, retry 6/120s, throttle 100ms)
├── model_router.py           — task-type routing across providers (P1-4, m7-pr28)
├── cache.py                  — prompt cache: in-process LRU + Redis (cost econ)
├── application_brief.py      — Pydantic ApplicationBrief: input contract for all chains
├── agent_events.py           — event taxonomy emitted during agent runs
├── agents/
│   ├── __init__.py
│   ├── base.py               — BaseAgent (interface for every agent)
│   ├── contracts.py          — shared Pydantic contracts
│   ├── artifact_contracts.py — artifact (CV, cover letter, etc.) shapes
│   ├── agentic_event_emitter.py — emits stage.* events to subscribers (SSE)
│   ├── build_planner.py      — plans the per-application build
│   ├── critic.py             — quality gate (factual + ATS)
│   ├── drafter.py            — generic drafter primitive
│   ├── eval.py               — gold-set evaluator
│   ├── evidence.py           — evidence ledger
│   ├── evidence_graph.py     — provenance graph (chunk -> claim)
│   ├── fact_checker.py       — verifies claims against source
│   ├── lock.py               — per-stage advisory lock
│   ├── memory.py             — short-term agent memory
│   ├── multi_pipeline.py     — fans out multiple variants (A/B Lab)
│   ├── observability.py      — OTEL spans + langfuse traces
│   ├── optimizer.py          — re-prompt-if-poor heuristic
│   ├── event_taxonomy.py     — declares emitted event types
│   ├── aim/                  — Application Intelligence Module agents
│   ├── culture_fit/          — culture-fit scoring agents
│   ├── interview_sim/        — interview simulator agents
│   ├── linkedin/             — LinkedIn-specific helpers
│   ├── networking/           — outreach / cold-message agents
│   ├── orchestration/        — phase orchestrators (Recon, Atlas, ...)
│   ├── portfolio/            — portfolio asset agents
│   ├── ppt/                  — slide-deck agents
│   └── salary/               — salary coach agents
├── chains/                   — 25 chains (RoleProfilerChain, GapAnalyzerChain, DocGeneratorChain,
│                                ATSScannerChain, CompanyIntelChain, DiscoveryChain, BenchmarkChain, ...)
├── data/                     — RAG ingestion + chunking (knowledge-svc seed)
├── evals/                    — eval harness, gold sets, regression gates
├── observability/            — OTEL bootstrap, prompt-version hashing
├── prompts/                  — prompt templates, versioned <name>.v<n>.txt
├── rag/                      — retrieval primitives, vector search
├── registry/                 — tool registry: dispatcher, resolvers (RESOLVERS allowlist)
├── schemas/                  — JSON schemas for tool I/O
├── tests/                    — pytest suite for AI runtime
└── tools/                    — concrete tool implementations (each declares sandbox_tier)
```

**Read first:** `api.py` (public surface), `model_router.py` (provider
selection), `agents/agentic_event_emitter.py` (how SSE events get out).

---

## `backend/` — FastAPI app

```
backend/
├── main.py                   — CANONICAL entrypoint (P1-6 SHIPPED — only one main.py)
├── Dockerfile
├── requirements.txt          — pinned ranges; min floors close CVEs
├── pytest.ini                — async mode, timeout 30s, xdist
├── VERSION                   — semver bumped on release
├── app/
│   ├── api/
│   │   ├── deps.py           — FastAPI dependencies (get_current_user, get_db, etc.)
│   │   └── routes/           — 50+ route files; one per surface
│   │       ├── auth.py, billing.py, candidates.py, generate/, applications.py, ...
│   │       ├── api_keys.py, webhooks.py, sse.py, agentic_stream.py
│   │       └── generate/jobs.py — TD-1: 1500+ lines; planned split
│   ├── core/
│   │   ├── security.py       — JWT verify, password hash, capability tokens
│   │   ├── observability.py  — OTEL bootstrap; MAX_SCRUB_DEPTH=16 (TD-2 SHIPPED)
│   │   ├── queue.py          — Redis Streams producer + consumer (P0-3 ACK on success)
│   │   ├── events/           — OutboxWriter, schemas, relay
│   │   ├── feature_flags.py  — flag registry + sunset checker
│   │   └── ...
│   ├── services/             — 60+ service modules (business logic)
│   │   ├── pipeline_runtime.py — orchestrator interface (Temporal/Redis/inprocess)
│   │   ├── usage_guard.py    — per-org daily $ cap (P0-4 SHIPPED — m12-pr08)
│   │   ├── cost_attribution.py — ai_invocations.cost_cents aggregator (P1-8)
│   │   ├── feature_flag_audit.py — append-only audit (P1-9 SHIPPED — m12-pr09)
│   │   ├── billing.py        — fail-closed in prod (TD-7 SHIPPED — m12-pr11)
│   │   └── ...
│   ├── temporal/
│   │   ├── client.py
│   │   ├── workflows/        — GenerationWorkflow, LongLivedSessionWorkflow, ...
│   │   └── activities/       — per-stage activities (P1-1 SHIPPED — m8-pr32)
│   ├── contexts/             — bounded contexts (Stage B target layout)
│   └── models/               — Pydantic + SQLAlchemy data models
└── tests/                    — 251 test files
    ├── ai/                   — provider failover, model router, cost cap (m12-pr12)
    ├── contracts/            — event schema contract test (CI-required)
    ├── security/             — tenancy isolation regression test (CI-required)
    ├── api/                  — route-level tests
    ├── integration/          — full-stack tests
    └── unit/
```

**Read first:** `main.py` (middleware order is load-bearing),
`services/pipeline_runtime.py` (which path runs), `core/queue.py` (queue
contract), `temporal/workflows/generation.py` (workflow shape).

---

## `frontend/` — Next.js 14 App Router

```
frontend/
├── package.json              — next 14.1.0, react 18.2.0, TanStack Query 5.17, ...
├── next.config.js
├── next-env.d.ts
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── playwright.config.ts      — E2E config (chromium/firefox/webkit)
├── vitest.config.ts          — unit test config
├── Dockerfile
├── public/                   — static assets
├── e2e/                      — Playwright specs
├── coverage/                 — vitest output (gitignored in CI)
├── output/                   — Next.js build output
├── scripts/                  — dev scripts (sdk drift check, etc.)
└── src/
    ├── app/
    │   ├── (auth)/           — login, register, password reset
    │   ├── (dashboard)/      — 30+ dashboard pages: dashboard, applications,
    │   │                       ats-scanner, builder, career, candidates,
    │   │                       interview, salary, learning, evidence, gaps,
    │   │                       insights, knowledge, ppt, ab-lab, batch,
    │   │                       benchmark, consultant, export, job-board,
    │   │                       new, nexus, settings, skills,
    │   │                       tracked-companies, upload, api-keys, ...
    │   ├── api/              — Next.js API routes (proxy / auth helpers)
    │   ├── layout.tsx
    │   └── page.tsx
    ├── components/           — shared UI (shadcn-style)
    │   ├── ui/               — primitives (Button, Card, Dialog, ...)
    │   ├── pipeline/         — Mission-Control UI: per-agent panels
    │   ├── editor/           — TipTap editor
    │   └── ...
    ├── lib/
    │   ├── api/              — generated OpenAPI SDK + hand-written clients
    │   ├── sseClient.ts      — ONLY allowed SSE wrapper (raw EventSource forbidden)
    │   ├── supabaseClient.ts — Supabase browser client
    │   ├── firestore/        — MISNAMED: actually Supabase data layer (legacy)
    │   ├── auth/             — auth helpers, JWT decode
    │   └── ...
    ├── modules/              — feature modules (mission, evidence, ...)
    └── styles/               — globals.css, tokens
```

**Read first:** `lib/sseClient.ts` (streaming contract), one route in
`app/(dashboard)/` to see the pattern, `components/pipeline/` for the
Mission-Control UI.

**Watch out:** `lib/firestore/` is a misleading name — it's the Supabase data
layer. We migrated off Firestore early in the project; the folder name was
not renamed.

---

## `supabase/` — Database

```
supabase/
├── config.toml               — Supabase CLI config
├── seed.sql                  — local dev seed
└── migrations/               — 61 migrations, single root (P1-5 SHIPPED)
                                naming: YYYYMMDDHHMMSS_<slug>.sql
                                range: 20260206000000 -> 20260502010000
```

Single migration root is enforced; `database/` no longer exists. See
[DATABASE_CONTEXT.md](DATABASE_CONTEXT.md) for the full table inventory.

---

## `packages/` — Shared schemas

```
packages/
└── events/
    ├── schema/v1/            — JSON schemas for canonical event types (~30 types)
    └── scripts/codegen.py    — generates Python / TS / Kotlin types from schemas
```

`make events-codegen` regenerates language bindings. Producers and consumers
import from generated; never hand-define an event payload.

---

## `infra/` — Local + staging infrastructure

```
infra/
├── docker-compose.yml        — local dev stack (Postgres, Redis, Temporal)
├── Dockerfile.backend
├── Dockerfile.frontend
├── staging-mirror.compose.yml — P1-15 SHIPPED (m11-pr45) production mirror
└── observability/            — Prometheus / Grafana / OTEL collector configs
```

---

## `config/` — Static config

```
config/
└── feature_flags.yaml        — 12+ flags with owner/created/sunset/default/purpose
```

CI fails if any flag is past its sunset date by 14+ days
(`scripts/governance/check_feature_flags.py`).

---

## `docs/` — Documentation

```
docs/
├── ARCHITECTURE.md           — narrative overview (cross-refs blueprint)
├── PROJECT_JOURNAL.md        — chronological build log
├── SLO.md                    — golden SLOs
├── _archive/                 — retired *_PLAN.md files (TD-6 SHIPPED)
├── adrs/                     — 25 ADRs (0001 -> 0041)
├── architecture/
│   ├── WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md  — 1200 lines, 25 sections (canonical)
│   ├── SCALING_PHASES.md     — Stage A/B/C plan
│   ├── PRODUCTION_READINESS_CHECKLIST.md
│   └── ENGINEERING_GUARDRAILS.md
├── runbooks/                 — 6 runbooks
│   ├── cache-degraded-mode.md
│   ├── circuit-breaker-recovery.md
│   ├── dlq-replay.md
│   ├── observability.md
│   ├── outbox-partitions.md
│   └── staging-schema-sync.md
└── superpowers/              — internal skill notes
```

---

## `scripts/` — Ops, governance, dev

```
scripts/
├── backfill_*.py             — historical data backfills
├── check_chains.py
├── health_check.py
├── HireStack_AI_Analysis.js
├── run_migrations.py
├── smoke_test.py
├── test_auth_quick.py, test_auth_security.py
├── test_module*.py           — per-module smoke tests
├── test_streaming_fix.py
├── dev/                      — developer one-offs
├── governance/               — feature_flag sunset checker, context-freshness checker (this PR)
└── ops/                      — production ops scripts
```

---

## `tools/` — Build-time helpers

```
tools/
├── codegen/                  — schema -> code (also see packages/events/scripts/)
└── codemods/                 — bulk refactors (jscodeshift, libcst, etc.)
```

---

## `k6/` — Load tests

```
k6/
├── config.js
├── flows.js
├── scenarios/                — k6 scenarios per surface
└── README.md
```

---

## `mobile/` — Native Android

```
mobile/
├── README.md, SIDELOAD.md
├── android/                  — Native Kotlin app
└── lib/                      — Future shared client (Kotlin Multiplatform target, Stage B)
```

---

## `output/` — Runtime output (gitignored)

Created by generation runs and analysis scripts. Not source.

---

## "Where do I put this?" cheat sheet

| New thing | Goes in | Then update |
|---|---|---|
| New REST route | `backend/app/api/routes/<surface>.py` (or new file) | [API_CONTEXT.md](API_CONTEXT.md), regen frontend SDK |
| New service / business logic | `backend/app/services/<domain>.py` | [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md) |
| New AI agent | `ai_engine/agents/<domain>/` (or root for primitive) | [AI_CONTEXT.md](AI_CONTEXT.md) |
| New AI chain | `ai_engine/chains/<chain>.py` | [AI_CONTEXT.md](AI_CONTEXT.md) |
| New tool | `ai_engine/tools/<tool>.py` + `ai_engine/registry/resolvers.py` entry + `ai_tools` row with `sandbox_tier` | [AI_CONTEXT.md](AI_CONTEXT.md), [AUTH_SECURITY_CONTEXT.md](AUTH_SECURITY_CONTEXT.md) |
| New event type | `packages/events/schema/v1/<event>.json` then `make events-codegen` | [API_CONTEXT.md](API_CONTEXT.md) §events |
| New DB table | `supabase/migrations/<ts>_<slug>.sql` with RLS | [DATABASE_CONTEXT.md](DATABASE_CONTEXT.md) |
| New Temporal workflow | `backend/app/temporal/workflows/<name>.py` + activities | [BACKEND_CONTEXT.md](BACKEND_CONTEXT.md) |
| New runbook | `docs/runbooks/<name>.md` | [KNOWN_ISSUES.md](KNOWN_ISSUES.md) if new failure mode |
| New ADR | `docs/adrs/00NN-<slug>.md` | this file's ADR index, [ARCHITECTURE.md](ARCHITECTURE.md) |
| New feature flag | `config/feature_flags.yaml` with owner / sunset | flag is auto-snapshotted by audit service |
| New context doc | `context/<NAME>.md` | this file's index |
