# HireStack AI Platform Advantage Roadmap

Date: 2026-04-11

## Thesis

HireStack should not compete as a generic AI resume builder. The durable advantage is a career operating system with three properties that most products do not have at the same time:

1. Evidence-grounded outputs instead of style-first generation.
2. Stateful multi-agent execution instead of single-prompt composition.
3. Closed-loop quality learning from user outcomes, reviewer feedback, and evaluation corpora.

If we execute well, the moat is not the prompt text. The moat is the system:

- reusable evidence graph
- durable workflow runtime
- adaptive agent planner
- eval harness with gold cases and live failure replay
- user and recruiter outcome data
- workspace UX that makes the system trustworthy and fast

## What “Years Ahead” Actually Means

Within 12 months, HireStack should be able to do five things materially better than competitors:

1. Prove where every important claim came from.
2. Resume and recover long-running work without losing state.
3. Personalize document strategy and coaching from prior successful outcomes.
4. Improve agent quality continuously through offline evals and live telemetry.
5. Expand from application generation into a full candidate operating system.

## Strategic Pillars

### 1. Agent Operating System

The agent layer should evolve from a pipeline into an execution substrate.

Required capabilities:

- durable checkpoints and artifact rehydration
- adaptive stage planning by task, profile quality, and JD quality
- stage-level cost, latency, and failure policies
- controlled tool use with contracts at every boundary
- explicit quality gates before delivery

Target outcome:

- any document job can be resumed, inspected, replayed, and judged deterministically

### 2. Evidence Graph and Truth Layer

The current evidence ledger is the right direction. It should become the canonical truth system for the platform.

Next capabilities:

- job-scoped and user-scoped evidence identities
- claim-to-evidence graph persistence
- contradiction detection across resume, profile, LinkedIn, and generated outputs
- evidence freshness and confidence scoring
- reusable proof objects that travel across CV, cover letter, portfolio, interview answers, and salary narratives

Target outcome:

- HireStack becomes the safest and most trustworthy AI application platform in the market

### 3. Continuous Evaluation Loop

Every serious AI product wins on eval discipline.

Required capabilities:

- gold corpus for each pipeline and each agent
- regression suites for failure classes, not only happy paths
- replay runner for failed production jobs
- pairwise judging for document variants
- outcome-linked scoring from user exports, recruiter responses, interview conversions, and placements

Target outcome:

- quality becomes measurable, not anecdotal

### 4. Personalization and Memory

The platform should learn stable user preferences and successful strategies.

Required capabilities:

- user-specific tone and structure preferences
- role-family strategy memories
- company-family strategy memories
- feedback learning from accepted or rejected variants
- memory safety rules so preference never overrides factual truth

Target outcome:

- documents feel individually coached, not merely tailored

### 5. Career Workspace as Mission Control

The frontend advantage should be operational clarity, not flashy generation.

Required capabilities:

- live agent timeline with evidence and decisions
- confidence and risk surfaces, not opaque spinners
- action queue that connects gaps to learning plans to evidence collection
- version comparison and why-this-changed explainability
- recruiter mode and enterprise candidate pipeline views

Target outcome:

- the user sees the system as a career cockpit, not a one-off generator

## Execution Plan

### Horizon 1: 0-30 Days

Objective: make the current core unambiguously reliable.

Must ship:

- remove latent runtime bugs in evidence and citation flow
- refresh fact-check and citation state after revisions
- make observability reflect actual revision-loop cost
- finish true artifact-backed resume across all document pipelines
- add replayable eval cases for the top ten production failure modes
- make provider behavior and platform docs match reality

Success metrics:

- zero known latent core-path runtime exceptions
- 95%+ deterministic recovery for interrupted document jobs
- 100% of final delivered documents have a fresh validation report and current citations

### Horizon 2: 30-90 Days

Objective: move from “good pipeline” to “self-improving system.”

Must ship:

- adaptive planner that chooses stages and tools by context quality
- memory write-back with usefulness scoring
- variant lab with pairwise judging and winner promotion
- production replay harness for failed jobs
- evidence quality scoring and contradiction detection
- company and role strategy packs with measurable lift

Success metrics:

- measurable lift in document quality scores and ATS score deltas
- lower token cost per successful generation
- lower revision count per accepted output

### Horizon 3: 90-180 Days

Objective: create a defensible platform moat.

Must ship:

- candidate knowledge graph across profile, evidence, applications, interviews, salary plans, and outcomes
- recruiter intelligence and agency workflows built on the same truth layer
- learning engine that closes the gap between missing skills, proof collection, and applications
- benchmarked simulation environment for role families and markets
- API and enterprise analytics surfaces built on auditable agent artifacts

Success metrics:

- materially better interview and response conversion than baseline workflows
- enterprise users adopt HireStack for candidate operations, not just document generation

## Immediate Technical Priorities

1. Core truth guarantees
   - every final validator run must consume current citations and current fact-check state
   - all evidence writes must be type-safe and job-safe

2. Runtime resilience
   - resume must be artifact-backed, not stage-skipping only
   - recovery must be isolated per pipeline within a multi-document job

3. Quality telemetry
   - revision loops, retries, and re-checks must be visible in metrics
   - every failure class should have a replay path and an owning regression test

4. Personalization infrastructure
   - start storing stable preference primitives, not raw prompt fragments
   - track which strategies correlate with successful user outcomes

## Product Design Principles

1. Trust over flair
   - users will forgive slower generation before they forgive fabricated content.

2. Explainability by default
   - every important suggestion, warning, and change should have a why.

3. Deterministic where possible
   - use AI for synthesis and judgment, not for arithmetic, parsing, or state accounting.

4. Human escalation as a feature
   - the platform should know when confidence is low and guide the user explicitly.

5. Reusable system value
   - every artifact should be reusable across multiple workflows, not trapped in one generation run.

## Operating Cadence

Weekly:

- review replay failures
- review contract drift
- review evidence coverage and fabricated-claim rate
- review export-to-response funnel changes

Monthly:

- refresh gold corpus
- re-rank roadmap bets based on measurable lift
- cut dead features that do not improve trust, speed, or outcomes

## Bottom Line

The way to be years ahead is not to chase more agent names or more prompt complexity. It is to build the best evidence-grounded, stateful, continuously improving career intelligence platform in the market.

That means:

- truth layer first
- runtime reliability second
- evaluation loop third
- personalization and enterprise scale on top of that

Everything else is packaging.

---

## Architecture Decision Records (ADRs)

### ADR-001: Multi-Model Cascade Failover

**Date:** 2026-04-12  
**Status:** Implemented  
**Context:** The platform relied on a single model (gemini-2.5-pro) for all AI tasks. Any quota exhaustion, rate limit, or service degradation caused total generation failure.  
**Decision:** Implement a cascade failover router in `ai_engine/model_router.py` with:
- Cost-optimized routing: validation/critique → flash, reasoning/research → pro
- Ordered fallback lists per task type (`MODEL_CASCADE` env var override)
- Per-model health tracking with auto-recovery (3 failures → unhealthy, 120s recovery)
- `AIClient.complete/complete_json/chat` now loop through cascade, catching failures and falling back

**Consequences:**
- Generation survives quota exhaustion on primary model
- Cost reduction on lightweight tasks routed to flash
- Health status visible in `/health` endpoint
- Zero breaking changes — existing callers are unaffected

### ADR-002: DB Connection Pooling

**Date:** 2026-04-12  
**Status:** Implemented  
**Context:** The Supabase connection pooler was disabled (`db.pooler.enabled = false`), meaning every PostgREST request opened a new database connection. Under concurrent generation jobs, this caused connection exhaustion.  
**Decision:** Enable PgBouncer transaction-mode pooling in `supabase/config.toml` with pool_size=20 and max_client_conn=100.

**Consequences:**
- Connection reuse reduces PostgreSQL load under concurrency
- Transaction-mode compatible with all existing queries (no prepared statements across transactions)
- 100 concurrent client connections safely served by 20 actual DB connections

### ADR-003: Redis Response Cache with In-Memory Fallback

**Date:** 2026-04-12  
**Status:** Implemented  
**Context:** Read-heavy endpoints (profile, applications list, evidence) hit PostgreSQL on every request. No caching layer existed.  
**Decision:** Add Redis-backed caching utilities to `backend/app/core/database.py`:
- `get_redis()`: lazy connection with timeout-bounded initialization
- `cache_get/cache_set/cache_invalidate/cache_invalidate_prefix`: async helpers
- In-memory LRU fallback (512 entries) when Redis is unavailable
- Configurable via `CACHE_TTL_SECONDS` and `CACHE_ENABLED` env vars

**Consequences:**
- Route handlers can opt-in to caching with simple `cache_get`/`cache_set` calls
- Graceful degradation: falls back to in-memory when Redis is down
- Cache invalidation primitives ready for write-through patterns

### ADR-004: Enhanced Health Endpoint

**Date:** 2026-04-12  
**Status:** Implemented  
**Context:** The `/health` endpoint reported Supabase and circuit breaker status but not Redis or model health.  
**Decision:** Extend the health endpoint with:
- Redis connectivity check
- Model cascade health status from `model_router.get_model_health()`
- Active generation task count visibility

**Consequences:**
- Railway health checks and monitoring dashboards get full system observability
- Degraded model or Redis state is immediately visible

### ADR-005: Graceful Shutdown for Generation Tasks

**Date:** 2026-04-12  
**Status:** Implemented  
**Context:** On SIGTERM (Railway deploys), the API process drained HTTP connections but abandoned in-flight generation tasks. These became orphaned jobs that required periodic cleanup.  
**Decision:** During shutdown, cancel all active generation tasks and await their completion before releasing resources.

**Consequences:**
- Generation tasks receive `CancelledError` and finalize their job status in DB
- Fewer orphaned jobs after deployments
- Cleaner process shutdown sequence