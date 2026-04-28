# HireStack AI — Production-Readiness Squad Plan

**Date**: 2026-04-28
**Owner**: Platform Leadership
**Goal**: Ship a production-grade, scale-ready, best-in-class platform by dividing work across 12 focused squads, each delivering a hardened, gap-closed, scale-ready slice.

This document is the **organizational blueprint** for completing the platform. The companion execution plan walks each squad through Audit → Fix → Upgrade → Harden → Sign-off in a single pass, then re-verifies cross-cutting concerns at the end.

---

## How This Is Organized

Each squad owns:
1. **Charter** — what they own and why it matters.
2. **Surface area** — primary files/dirs, entry points, current LOC.
3. **Production targets** — what "done" looks like.
4. **Known gaps & tech debt** — the backlog they must close.
5. **Scale & resilience asks** — what changes to survive 10x and 100x growth.

Squads are sequenced for dependency safety (foundations first), but most can execute in parallel within a phase.

---

## Squad Roster (12 Squads)

| # | Squad | Domain | Tier | Files (approx) | LOC | Sequencing |
|---|-------|--------|------|----------------|-----|------------|
| S1 | Platform Core | Backend foundations: app bootstrap, config, security, deps, middleware | L | 10 core + main.py | ~2k | Phase 1 |
| S2 | Data & Migrations | Supabase schema, migration hygiene, RLS, integrity invariants | M | 40 migrations | ~3k SQL | Phase 1 |
| S3 | Pipeline Runtime | `pipeline_runtime.py`, EventSinks, phase orchestration, critic gates | L | 1 mega-file + helpers | ~4.3k | Phase 1 |
| S4 | Generation API & SSE | `/pipeline/stream`, `/generate/jobs`, job runner, SSE downgrade | XL | jobs.py, stream.py, helpers.py | ~4.3k | Phase 2 |
| S5 | AI Engine — Chains | Tier-1/2/3 chains, prompts, schemas | L | 25 chains | ~8k | Phase 2 |
| S6 | AI Engine — Agents & Eval | Agents, validation_critic, model_router, evals | L | 15 agents | ~7k | Phase 2 |
| S7 | Domain Services | 40 backend services (docs, evidence, exports, ATS, etc.) | L | 40 services | ~12k | Phase 2 |
| S8 | Frontend Web | Next.js app, dashboard pages, components, hooks, firestore lib | XL | 300+ files | ~18k | Phase 3 |
| S9 | Mobile (Android) | Kotlin app, networking, screens, state | M | Kotlin tree | ~15k | Phase 3 |
| S10 | Infra & Deploy | Dockerfiles, Railway, Netlify, Procfile, CI/CD, staging | S | infra/, root configs | ~1k | Phase 4 |
| S11 | Observability & SRE | Sentry, logs, metrics, SLOs, alerts, runbooks | M | tracing, metrics, dashboards | ~1k | Phase 4 |
| S12 | QA & Release Engineering | Unit/integration/e2e/load test suites, release gates, smoke runs | M | tests across stacks | ~5k | Phase 4 |

**Cross-cutting working groups** (small, span all squads):
- CCWG-Sec — security & compliance review (auth, RLS, secrets, OWASP).
- CCWG-Perf — performance & cost (latency budgets, model routing, caching).
- CCWG-DocsKB — `docs/` cleanup, runbook authoring, ADRs.

---

## S1 — Platform Core
**Charter**: Own the backend foundation everyone else depends on. Make startup, config, auth, middleware, error handling, and request lifecycle bulletproof.

**Surface area**:
- `backend/main.py`, `backend/app/__init__.py`
- `backend/app/core/`: config.py, database.py, security.py, tracing.py, metrics.py, circuit_breaker.py, feature_flags.py, queue.py
- `backend/app/api/deps.py`, `backend/app/api/response.py`

**Production targets**:
- Single source of truth for settings; no scattered `os.getenv` in services.
- Auth middleware paths fully covered by tests; JWT verification fast-path benchmarked.
- Request-ID/trace propagation end-to-end (HTTP → DB → AI calls).
- Circuit breaker around every external dependency (Supabase, Gemini, Stripe).
- Feature-flag system wired to a real backing store, not just env.

**Known gaps**:
- `database.py` ~400 LOC mixes client init + JWT + TABLES dict — split.
- Inconsistent response envelope across legacy routes.
- `deps.py` auth helpers branch on env in surprising ways.

**Scale asks**:
- Connection pooling tuned for Railway; retry policies documented.
- Cold-start lazy imports audited.
- Health endpoint deep-checks (DB, Redis, AI provider) with separate `/healthz/live` vs `/healthz/ready`.

---

## S2 — Data & Migrations
**Charter**: One trusted schema. Zero drift between repo and prod. Integrity invariants enforced in DB, not just app code.

**Surface area**:
- `database/`, `supabase/migrations/`
- Cascade rules, RLS policies, indexes
- `database.py` TABLES map alignment

**Production targets**:
- All committed migrations applied to staging and prod; recorded in a migration ledger.
- RLS enabled and audited on every user-scoped table.
- Foreign keys + ON DELETE CASCADE semantics verified for org delete and job lifecycle.
- Indexes covering hot read paths (jobs by user, document_library by app, evidence by job).
- Pruned dead/duplicate migrations and consolidated `apply_*` SQL files.

**Known gaps**:
- 40+ migration files with overlapping naming; a few unapplied (e.g., `20260422000000_widen_generation_jobs_status.sql`).
- TABLES dict drift documented in `frontend-access-model-remnants.md` and `schema-drift-2026-04-21.md`.
- `combined_migration.sql`, `apply_all_pending.sql` etc. are dangerous if mis-run.

**Scale asks**:
- Read replicas plan; pgbouncer / Supabase pooler verification.
- pg_stat_statements review for top 50 queries.
- Partitioning strategy for events/analytics tables once they pass 10M rows.

---

## S3 — Pipeline Runtime
**Charter**: The heart of the platform. Make the orchestrator small, observable, and impossible to break.

**Surface area**:
- `backend/app/services/pipeline_runtime.py` (~4.3k LOC, 1 file — biggest hotspot)
- `backend/app/services/event_bus_bridge.py`
- `backend/app/services/progress_calculator.py`
- Companion: `ai_engine/agent_events.py`

**Production targets**:
- File decomposed into focused modules: phases, sinks, runtime config, persistence, critic gates, finalize.
- Every public method has a behavioral test (already covered: `_run_critic_gate` Rank 14, `_persist_to_document_library` Rank 15, phase-order invariants).
- Deterministic phase timing; SLO budgets enforced with structured warnings.
- Idempotency for job restart; no duplicate document_library rows on retry.

**Known gaps**:
- One 4.3k-LOC file = high blast radius.
- `_build_evidence_summary`, `DatabaseSink.emit`, `_persist_status_payload` and similar still untested.
- Dual sink wrapping (`_ExecutionPathTaggingSink` + `CollectorSink`) is fragile — needs invariant tests.

**Scale asks**:
- Phase-level concurrency tuning (Atlas/Cipher fan-out budgets).
- Replace asyncio.gather chains with a small structured-concurrency helper.
- Backpressure when SSE consumer is slow; bounded event queue.

---

## S4 — Generation API & SSE
**Charter**: Real-time generation that never wedges. One canonical execution path. Predictable SSE semantics.

**Surface area**:
- `backend/app/api/routes/generate/jobs.py` (~2.1k LOC)
- `backend/app/api/routes/generate/stream.py` (~1k LOC)
- `backend/app/api/routes/generate/helpers.py` (~1.2k LOC)
- `backend/app/api/routes/generate/sync_pipeline.py`, `planned.py`, `cv_variants.py`, `document.py`, `schemas.py`

**Production targets**:
- jobs.py split into: job CRUD, runner, status finalize, retry. Each <500 LOC.
- stream.py split into: SSE endpoint, event router, downgrade rules.
- All three execution paths (sync, SSE, job-backed) call into the same PipelineRuntime — no logic drift.
- SSE protocol documented (event names, retry semantics, heartbeat, closing rules).

**Known gaps**:
- jobs.py is the largest file in the repo.
- Race conditions on concurrent /stream requests.
- "callback hell" 4-5 levels deep noted.

**Scale asks**:
- Stateless SSE workers behind sticky LB; job state in DB only.
- Resume-on-reconnect via last-event-id.
- Per-user concurrency caps and graceful 429 path.

---

## S5 — AI Engine — Chains
**Charter**: Every chain produces validated, schema-conformant output, with prompts under version control and quality measured.

**Surface area**:
- `ai_engine/chains/` (25 chains)
- `ai_engine/prompts/`, `ai_engine/schemas/`

**Production targets**:
- Every chain returns Pydantic-validated output; no raw dicts on hot paths.
- Prompt files version-tagged with eval scores; goldens checked in.
- Token budgets per chain documented; truncation strategy uniform.

**Known gaps**:
- Some chains predate the schema-first contract.
- Prompt files mixed Python literals + YAML — pick one.
- Eval coverage uneven.

**Scale asks**:
- Prompt cache hit-rate metrics surfaced.
- Multi-model routing per chain (cost vs. quality), not global.

---

## S6 — AI Engine — Agents & Eval
**Charter**: Agents are predictable, observable, and gated by a critic that catches regressions before users see them.

**Surface area**:
- `ai_engine/agents/` (15 agents incl. validation_critic, orchestrator, artifact_contracts)
- `ai_engine/model_router.py`
- `ai_engine/evals/`

**Production targets**:
- Critic gates cover all 5 review modes (Rank 14 done — extend to per-agent contracts).
- Model router fallback chain has a single tested code path.
- Eval harness runnable locally and in CI; baseline scores checked in.

**Known gaps**:
- `orchestrator.py` ~500 LOC — review for dead branches.
- Eval datasets sparse for cover_letter, personal_statement.

**Scale asks**:
- Per-tenant model overrides; bring-your-own-key path tested.
- Cost telemetry attached to every agent invocation.

---

## S7 — Domain Services
**Charter**: 40 services, all behaving consistently — same error model, same logging shape, same auth trust boundary.

**Surface area**:
- `backend/app/services/` excluding the runtime files owned by S3
- Notable: `document_library.py`, `artifact_store.py`, `org.py`, `evidence_mapper.py`, `quality_scorer.py`, `document_evolution.py`, `export.py`, `ats.py`, `billing.py`, `analytics.py`, `webhook.py`, `social_connector.py`, `job_sync.py`

**Production targets**:
- Each service has at least one happy-path + one failure-path test.
- Stripe + webhook flows reconciled; idempotency keys on every mutation.
- Export (PDF/DOCX) tested for known-tricky inputs (Unicode, RTL, oversized).
- ATS service benchmarked against a real ATS golden set.

**Known gaps**:
- `social_connector.py`, `job_sync.py` may have flaky external deps without backoff.
- Duplication between `document.py`, `document_evolution.py`, `document_catalog.py`, `doc_variant.py`.

**Scale asks**:
- Outbound HTTP via a single shared client with timeouts and retries.
- Background jobs for slow ops (export, social scrape).

---

## S8 — Frontend Web
**Charter**: A web app that loads fast, never shows stale state, and degrades gracefully when the backend is slow.

**Surface area**:
- `frontend/src/app/` (Next.js routes incl. `(dashboard)/applications/[id]/page.tsx`)
- `frontend/src/components/`, `frontend/src/lib/`, `frontend/src/hooks/`
- `frontend/src/lib/firestore/` (models, ops, queries)
- E2E in `frontend/e2e/`, unit in `frontend/src/__tests__/`

**Production targets**:
- Decompose oversized pages: `applications/[id]/page.tsx` (Intel + Overview tabs), homepage, pipeline-agent-view.
- Strict ModuleKey contract used everywhere; firestore models in lockstep with backend (resume now first-class — Rank 13 done).
- Type-check + lint green on every push; vitest + Playwright suites green.
- Lighthouse > 90 on landing + dashboard.

**Known gaps**:
- `applications/[id]/page.tsx` is hundreds of lines per tab.
- `firestore/ops.ts` 800+ LOC — many helpers; some defaults inconsistent.
- A11y not audited.

**Scale asks**:
- Code-split per route; defer heavy editors.
- React Query/SWR caching strategy reviewed; eliminate over-fetching.

---

## S9 — Mobile (Android)
**Charter**: A phone app that mirrors web functionality with a real native feel and offline-friendly state.

**Surface area**:
- `mobile/android/`
- Networking, screens, state management

**Production targets**:
- API contract parity: every web endpoint used by mobile has a typed Kotlin client.
- Auth flow rock-solid (refresh, biometrics).
- Offline view of cached docs.
- Crash-free sessions > 99.5%.

**Known gaps** (per repo memory `android-ui-waves-1-to-8.md`):
- UI waves 1-8 done; remaining waves not enumerated here.

**Scale asks**:
- ProGuard/R8 enabled; APK size budgeted.
- Background sync respects Doze.

---

## S10 — Infra & Deploy
**Charter**: A boring, repeatable, observable deploy. No more direct-to-prod.

**Surface area**:
- `infra/`, `Dockerfile.*`, `docker-compose.yml`, `Procfile`, `railway.toml`, `netlify.toml`, `Makefile`

**Production targets**:
- Dedicated **staging** environment that mirrors prod (DB, Redis, AI provider sandbox).
- CI pipeline: lint → typecheck → unit → integration → build → deploy-to-staging → smoke → manual gate → prod.
- Secrets in a real secret manager, not env files.
- Container image scanned for CVEs each build.

**Known gaps**:
- No staging today.
- Multiple Dockerfiles (`backend/Dockerfile`, `infra/Dockerfile.backend`) — collapse.
- `Procfile` + `railway.toml` overlap — clarify source of truth.

**Scale asks**:
- Horizontal scaling rules (Railway autoscale or migration plan).
- Blue/green or canary deploy.
- Disaster recovery runbook (RPO/RTO documented).

---

## S11 — Observability & SRE
**Charter**: Know when something is wrong before users do. Quantify everything.

**Surface area**:
- `backend/app/core/tracing.py`, `metrics.py`
- Sentry integration
- `analytics/`
- Dashboards (to be created)

**Production targets**:
- Per-phase latency dashboards; SLOs codified in `docs/SLO.md` and alerted on.
- Top-line business metrics: jobs/day, success rate, time-to-first-doc, Gemini cost/job.
- Structured JSON logs, sampled traces with correlation IDs.
- Error budget policy.

**Known gaps**:
- Logging is structured but dashboards aren't checked in.
- No alert routing playbook.

**Scale asks**:
- OpenTelemetry adoption (exporters configurable).
- Real-user monitoring on the frontend.

---

## S12 — QA & Release Engineering
**Charter**: Every release is provably better than the last. No regressions ship.

**Surface area**:
- `backend/tests/{unit,integration,e2e,smoke}/`
- `frontend/e2e/`, `frontend/src/__tests__/`
- `k6/` load scenarios
- `scripts/test_*.py` smoke scripts

**Production targets**:
- Backend unit suite stays green & fast (today: 1147 passing, ~6s — keep <15s).
- Integration suite runs against ephemeral DB; covers all generate/* paths.
- Playwright e2e covers: signup → create app → generate → export.
- k6 scenarios for SSE, job creation, export — baseline RPS published.
- A release-gate script that fails on coverage regression for hot files.

**Known gaps**:
- Many `scripts/test_*.py` look like ad-hoc smoke — graduate or delete.
- Frontend test coverage uneven.

**Scale asks**:
- Mutation testing on critical paths (pipeline_runtime, validation_critic, billing).
- Contract tests between frontend Firestore models and backend payloads.

---

## Cross-Cutting Working Groups

### CCWG-Sec
- OWASP Top 10 sweep on every public route.
- Auth/JWT replay protection; CSRF/SSRF/SQLi audit.
- Secrets rotation playbook.
- RLS audit against every user-scoped table.
- Dependency scanning (pip-audit, npm audit, Trivy).

### CCWG-Perf
- Latency budget per phase (recon=8s, atlas=12s, cipher=10s, quill=20s, forge=15s, sentinel=5s, nova=2s, persist=5s) — instrument & alert.
- Model routing cost dashboard.
- Cache hit rate per chain.
- Frontend bundle budgets.

### CCWG-DocsKB
- Prune `docs/` (50+ markdowns, lots of duplication).
- ADRs for every architectural decision still standing.
- Single onboarding doc; runbooks per squad.

---

## Production-Ready Definition (acceptance for "done")
A squad is **production-ready** only when ALL of:
1. **Coverage** — behavioral tests on every public function in their scope.
2. **Observability** — structured logs + at least one dashboard panel + at least one alert.
3. **Resilience** — failure-mode tests (timeout, 5xx, malformed input) for every external dep.
4. **Performance** — latency p50/p95 measured and within budget under k6 baseline.
5. **Security** — CCWG-Sec sign-off; secrets externalized; RLS verified.
6. **Docs** — runbook + ADRs + clear onboarding for the next engineer.
7. **Release gate** — green CI from clean clone to deploy on staging, then prod, in one command.

---

## Execution Sequencing (high level)

| Phase | Squads in flight | Goal |
|-------|------------------|------|
| Phase 1 — Foundations | S1, S2, S3 | Make the substrate trustworthy. |
| Phase 2 — Generation Backbone | S4, S5, S6, S7 | All generation paths converge on one runtime. |
| Phase 3 — Surfaces | S8, S9 | UI parity & polish on web + mobile. |
| Phase 4 — Operate | S10, S11, S12 | Staging, alerts, gates. Production posture. |
| Phase 5 — Cross-cutting sweep | CCWG-Sec, CCWG-Perf, CCWG-DocsKB | Final hardening pass. |
| Phase 6 — Production cutover | All | Promote to prod, monitor, retro. |

---

## Per-Squad Execution Pass (5 steps each)

Every squad runs the same 5-step loop, in order:

1. **Audit** → produce `docs/audits/S{N}-{slug}.md` listing gaps, dead code, security concerns, dependency CVEs, oversized files, missing tests. Read-only.
2. **Fix** → close defects and inconsistencies surfaced by the audit. Each PR ≤500 LOC, each PR adds at least one behavioral test.
3. **Upgrade** → bring code up to the squad's production targets (decomposition, schema-first, contracts, etc.).
4. **Harden** → resilience, observability, performance, security work.
5. **Sign-off** → check the 7-point Production-Ready bar; record in `docs/audits/S{N}-signoff.md`.

**Verification gate after every PR**: backend unit suite stays green and stays under 15s wall-clock (baseline: 1147 passing, ~6.5s).

---

## Defaults in Effect

- **Concurrency**: parallel within a phase; serial across phases.
- **Push policy**: 16 local commits stay local until P4-S10 lands a working staging deploy; then pushed as one tagged release.
- **CI host**: GitHub Actions (configured in P4-S10 / P4-S12).
