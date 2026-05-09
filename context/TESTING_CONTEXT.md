---
title: Testing Context
last_synced: 2026-05-09
watch_paths:
  - backend/tests
  - ai_engine/tests
  - frontend/src
  - frontend/e2e
  - frontend/vitest.config.ts
  - frontend/playwright.config.ts
  - backend/pytest.ini
  - conftest.py
canonical_sources:
  - CONTRIBUTING.md
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#19-quality-gates
update_when:
  - a new test category is added (contract, mutation, soak)
  - a CI gate is promoted from informational to required
  - the coverage threshold changes
  - the Playwright or vitest config changes
  - a new pytest plugin / marker is introduced
---

# Testing Context

> Tests are the **contract** between humans and the agentic system. We
> test for behavior, not implementation, but we ALSO test for the
> non-negotiables that no LLM can re-prove (RLS isolation, idempotency,
> SSRF safety, prompt-version stability).

---

## TL;DR — 12 lines

1. **Backend test count:** 251 tests today (pytest, asyncio, xdist
   parallel, 30s default timeout).
2. **Frontend test count:** vitest unit (fast) + Playwright E2E.
3. **Test pyramid weighted toward integration:** the LLM behavior is
   stochastic, so contract tests + golden-set evals do most of the work.
4. **Required CI gates** (must pass to merge): tenancy isolation, eval
   regression, secret scan, OpenAPI drift, dep audit, coverage,
   import-linter, migrations dry-run, backend tests, frontend tests, e2e.
5. **Tenancy isolation is the most important test in the repo.** It
   proves no PR added an org_id leak. It runs first; failure short-
   circuits CI.
6. **Eval gate runs only chains touched in the PR.** Nightly full sweep
   posts trends.
7. **Coverage thresholds** (m12-pr02): backend ≥ 75%, frontend ≥ 70%.
   Per-package thresholds tighter for critical packages
   (`backend/app/api/middleware/`, `ai_engine/registry/`).
8. **No live-network tests.** External calls are mocked via `respx`
   (httpx) or `responses` (requests). Provider responses are recorded
   fixtures.
9. **No real LLM calls in unit tests.** The model client is replaced by
   `FakeLLMClient` returning fixture completions.
10. **Mutation testing is NOT in CI yet** (TD-8 open). Stage B work.
11. **Soak / load tests** run separately via `k6/` against staging mirror
    (not in PR CI).
12. **Test data** is generated, not committed. Fixture builders under
    `backend/tests/factories/`.

---

## Backend tests (`backend/tests/`)

Layout:

```
backend/tests/
  conftest.py                # global fixtures (db, jwt, http client)
  factories/                 # data builders (users, orgs, applications)
  api/                       # route tests (per route file)
  services/                  # service-layer tests
  middleware/                # middleware tests (idempotency, slowapi, etc.)
  security/                  # tenancy isolation, jwt, ssrf, idempotency
  billing/                   # usage_guard, quotas, cost cap
  pipeline/                  # GenerationWorkflow integration tests
  queue/                     # Redis Streams tests, DLQ tests
  db/                        # migrations, partition health
  contract/                  # event schema contract tests
```

`backend/pytest.ini`:

- `addopts = -ra --strict-markers -n auto --timeout=30 --maxfail=5`
- `asyncio_mode = auto`
- markers: `slow`, `integration`, `requires_db`, `requires_redis`,
  `requires_temporal`, `golden`

Database fixture: per-test transaction; rollback at teardown. Faster than
recreating the schema.

JWT fixture: signs a test JWT with org_id, user_id, scopes. Per-test
rebuild so RLS context is clean.

---

## AI engine tests (`ai_engine/tests/`)

```
ai_engine/tests/
  agents/      # agent unit tests (with FakeLLMClient)
  chains/      # chain unit tests
  tools/       # tool tests (with safe_fetch fixtures)
  evals/       # gold sets per chain + regression harness
  registry/    # tool registry + capability token tests
```

Gold sets:

- One JSON file per chain under `ai_engine/evals/golds/<chain>.jsonl`.
- Each line: `{ "input": ..., "expected": ..., "scoring": {...} }`.
- Eval runner re-runs the chain with `FakeLLMClient` set to record mode in
  staging (real model) or replay mode in CI.
- Scoring: `rouge`, `bleu`, model-judge (GPT-4 or Gemini Flash) for prose;
  exact match for structured outputs.

Regression detection: per-chain quality score baseline stored in
`ai_engine/evals/baselines/`. PR diff > 5pp triggers eval gate failure.

---

## Frontend tests (`frontend/`)

`vitest.config.ts`:

- Unit tests for hooks, utility functions, components (RTL).
- jsdom environment for component tests.
- Coverage via `@vitest/coverage-v8`.

`playwright.config.ts`:

- E2E tests under `frontend/e2e/`.
- Smoke tests per dashboard surface (login, generation, AIM, missions).
- Run against the staging mirror (compose) in CI.
- Visual regression: planned Stage B; not in CI yet.

Test data:

- Frontend tests stub the API via MSW (Mock Service Worker) for unit;
  E2E uses the real backend in staging mirror with seeded data.

---

## Required CI gates (the ones that MUST pass)

| Gate | Workflow | What it proves |
|---|---|---|
| **Tenancy isolation** | `tenancy-isolation.yml` | Cross-org data leak is impossible at SQL boundary |
| **Eval regression** | `eval-regression.yml` | Touched chains do not regress > 5pp |
| **Secret scan** | `secret-scan.yml` | No new secrets in code |
| **OpenAPI drift** | `openapi-drift.yml` | TS client matches backend OpenAPI |
| **Dep audit** | `dep-audit.yml` | No CVEs in `requirements.txt` / `package.json` |
| **Coverage** | `coverage.yml` | Backend ≥ 75%, frontend ≥ 70% |
| **Import linter** | `import-linter.yml` | `ai_engine` boundary intact |
| **Migrations check** | `migrations-check.yml` | Migration runs cleanly + RLS preserved |
| **Backend tests** | `backend-tests.yml` | 251 tests pass |
| **Frontend tests** | `frontend-tests.yml` | vitest + tsc + lint green |
| **E2E** | `e2e.yml` | Playwright smoke green (PR touching frontend) |
| **Lockfile freshness** | `ci.yml` (`lockfile-fresh` job) | `backend/requirements.lock` matches re-compiled output (TD-4, m12-pr14) |

Promoting a gate from informational to required = ADR.

---

## Tenancy isolation test (the load-bearing one)

`backend/tests/security/test_tenancy_isolation.py`:

```python
@pytest.mark.requires_db
async def test_no_cross_org_leak(db, two_orgs_with_overlapping_data):
    org_a, org_b = two_orgs_with_overlapping_data
    set_jwt_context(org_a)
    for table in MULTI_TENANT_TABLES:
        rows = await db.fetch(f"SELECT * FROM {table}")
        assert all(r["org_id"] == org_a.id for r in rows), \
            f"{table} returned org B data under org A JWT"
```

`MULTI_TENANT_TABLES` is auto-derived from the schema — any table with an
`org_id` column is checked. Adding such a table without an RLS policy =
the test fails on the new table = PR is blocked.

---

## Contract tests (`backend/tests/contract/`)

Event schemas under `packages/events/schema/v1/<event>.json` are
versioned. Contract tests:

1. Produce an event from a service.
2. Validate it against the JSON schema.
3. Consume it and assert the consumer parses it.

Schema breaking changes require:

1. New version directory (`packages/events/schema/v2/`).
2. Producer emits both v1 and v2 during a deprecation window (P1-9).
3. Consumers updated to v2.
4. v1 dropped after window.

Strict event validation gate (P1-7 SHIPPED — m7-pr31): unknown fields are
rejected (no silent drops).

---

## Idempotency, rate-limit, SSRF, RLS, JWT — focused tests

| File | What it covers |
|---|---|
| `tests/middleware/test_idempotency.py` | replay returns cached body; conflict on body change; TTL sweep |
| `tests/middleware/test_slowapi.py` | 60/minute decorator; 429 with Retry-After |
| `tests/security/test_safe_fetch.py` | private/loopback/link-local rejected; redirect re-validated; bandwidth budget |
| `tests/security/test_tenancy_isolation.py` | the big one |
| `tests/security/test_jwt_alg.py` | algorithm confusion blocked; RS256 enforced in prod env |

---

## Pipeline tests (`tests/pipeline/`)

- `test_generation_workflow.py` — happy path; per-stage activity boundaries.
- `test_resume_after_crash.py` — kill the worker mid-Quill; restart;
  assert Quill is not re-run (P1-1 SHIPPED).
- `test_provider_outage_failover.py` — Gemini breaker open; assert
  Anthropic takes over; assert `ai.model.choice` traces show fallback.

Planned (open):

- `tests/temporal/test_resume.py` — explicit Temporal-side resume test.
- `tests/queue/test_dlq.py` — DLQ enrollment + replay (TD-related).
- `tests/db/test_partition_health.py` — partition rotation.

---

## Eval gate mechanics

`scripts/governance/eval_gate.py` (planned location) — invoked by CI:

1. Diff PR against base; identify touched chains.
2. Run `ai_engine/evals/run.py --chain <chain>` for each.
3. Compare to baseline in `ai_engine/evals/baselines/<chain>.json`.
4. If quality score drops > 5pp, fail.
5. If quality score improves > 5pp, prompt the author to update baseline.

Nightly job runs the full sweep and posts a trend summary to a Slack
channel.

---

## Performance tests (k6)

`k6/scenarios/`:

- `gen_burst.js` — 50 RPS burst on `POST /api/generate/jobs`.
- `aim_lookup.js` — 200 RPS on `GET /api/aim/companies/:id`.
- `sse_stream.js` — 100 concurrent SSE consumers on
  `/api/generate/agentic-stream/{job_id}`.

Run against staging mirror or against staging environment (separate
`hirestack-staging` Railway project). Not in PR CI.

---

## Mutation testing (TD-8 open)

Not in CI today. Stage B plan: `mutmut` for backend, `stryker` for
frontend. Initial scope: `backend/app/api/middleware/`,
`ai_engine/registry/`, `backend/app/services/usage_guard.py`.

---

## Local test commands

`Makefile`:

```
make test                  # backend + frontend
make test-backend          # pytest -n auto
make test-frontend         # vitest run
make test-e2e              # playwright (requires staging-mirror up)
make test-tenancy          # the isolation test, fast
make eval                  # run all eval gold sets locally
make coverage              # coverage with html report
```

For a single test:

```
pytest backend/tests/api/test_applications.py::test_create_application -xvs
npx vitest run frontend/src/components/MissionCard.test.tsx
npx playwright test e2e/generation.spec.ts --headed
```

---

## What "good tests" look like in this repo

- [ ] New route has happy-path + auth-failure + rate-limit + idempotency
      tests.
- [ ] New service function has unit tests with all branches covered.
- [ ] New chain has a gold-set entry.
- [ ] New tool has a registry test + a sandbox-tier test.
- [ ] New migration has a `tenancy-isolation` re-run (auto-discovered).
- [ ] New event has a contract test.
- [ ] New SSE event has a strict-validation test.
- [ ] No `time.sleep` in tests — use `freezegun` or `asyncio` clock.
- [ ] No real network — `respx` / `responses` / MSW.
- [ ] Tests run < 1s each unless marked `slow`.
