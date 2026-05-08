# Engineering Guardrails

**Status:** Canonical · Enforced
**Companion to:** [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md)

This file enumerates **rules CI enforces** and **rules reviewers enforce**.
Violating a rule blocks the PR. Disagreeing with a rule requires an ADR.

---

## 1 · Governance Rules

### G1 · Single source of truth
The blueprint is canonical. Any architectural decision recorded only in chat, in a markdown plan at the repo root, or in a comment is **non-binding**. To make a decision binding:

1. Open a PR with the change.
2. Update the blueprint in the same PR.
3. Add or update an ADR using [`ADR_TEMPLATE.md`](./ADR_TEMPLATE.md).
4. Get architecture-WG review.

### G2 · No silent drift
A PR that deviates from the blueprint without updating the blueprint **is rejected**. The PR template's Architecture Impact section enforces this.

### G3 · ADR before implementation
Decisions of class "introduces a new external dependency", "changes a service boundary", "adds a workflow type", "changes the event schema in a breaking way", or "introduces a new tool sandbox tier" require an Accepted ADR **before** the implementation PR merges.

### G4 · Quarterly architecture review
Architecture-WG meets quarterly to:
- Walk the §18 P0/P1 register.
- Walk the §19 risk matrix.
- Walk the §20 tech debt register.
- Update SLO targets, error budgets, and the next-stage exit criteria.
- Mark stale ADRs as Deprecated.

---

## 2 · Coding Guardrails (CI-enforced)

### C1 · Forbidden anti-patterns (see blueprint §17)

A custom `ruff` plugin / `eslint` rule will fail the build for each. Until the plugin lands, code review enforces them.

- AP-1 long task in web pod
- AP-2 native EventSource
- AP-3 user-input concatenation into system prompt
- AP-4 `code_ref` outside `RESOLVERS`
- AP-5 unregistered event emission
- AP-6 unsafe migration
- AP-7 table without RLS
- AP-8 `datetime.now()` in workflow
- AP-9 single-provider AI dispatch
- AP-10 secret in source
- AP-11 in-memory rate limiter in prod
- AP-12 cross-context import
- AP-13 external dep without fallback
- AP-14 decision without ADR
- AP-15 unstructured LLM stage boundary
- AP-16 idempotency off
- AP-17 ACK before success
- AP-18 unmanaged partition

### C2 · Async discipline
- All I/O in async functions: `httpx.AsyncClient`, `asyncpg`, `aioredis`. Sync I/O inside async = blocked event loop = CI red.
- Bounded concurrency: every long-running task spawn must use a `Semaphore` or task group with explicit cap.
- No `asyncio.create_task(...)` without keeping the reference + cancellation hook + bound.

### C3 · Type discipline
- Every public function in `ai_engine/` and `backend/app/contexts/` is typed.
- Pydantic models for every API request, response, event, and activity boundary.
- `mypy --strict` on `ai_engine/` (Stage A end target).

### C4 · Logging discipline
- `structlog` only. No `print`. No raw `logging.info("user %s", ...)` with PII.
- PII fields go through redactor. Add new sensitive keys to the redactor allowlist; CI tests the redactor against fixtures.

### C5 · Configuration discipline
- All config via Pydantic `Settings`. No `os.environ.get` scattered.
- Required-in-prod values fail fast at startup.
- A single `Settings` instance per process, injected via DI.

### C6 · DB discipline
- `asyncpg` via service helpers, never raw `psycopg2`.
- No raw SQL in route handlers — go through a context's repository module.
- All migrations expand→migrate→contract; never rename/drop in one step.
- New table → RLS policy in same migration → CI test asserts RLS enabled.

### C7 · LLM discipline
- All model calls go through `ai_engine/client.py`.
- All model calls write `ai_invocations` row.
- All model calls go through `model_router` (no hardcoded model id).
- All prompts versioned (filename `<name>.v<n>.txt`).
- All structured outputs validated by JSON Schema **inside** the agent before returning to caller.

### C8 · Frontend discipline
- All SSE via `@microsoft/fetch-event-source` (not native `EventSource`).
- All API calls through a generated client (target: orval/openapi-typescript-codegen).
- No hand-typed API response shapes.

### C9 · Test discipline
- Tests are deterministic. No live network in unit tests; mock or testcontainer.
- No `time.sleep` to wait for async — use `asyncio.wait_for` or polling helpers.
- Snapshot tests for prompts use named fixture files, not inline strings.

### C10 · Dependency discipline
- New dep requires:
  - License check (MIT/Apache/BSD only without legal review)
  - Maintenance check (commit in last 12 months)
  - Single-vendor risk noted
  - Security advisory subscribed
- Pinned in `requirements.lock` (Stage A end target)
- Removed within 30 days if unused (auto-PR via dependabot).

---

## 3 · Process Guardrails

### P1 · One concern per PR
A PR introduces one architectural change. "Refactor + add feature" = two PRs.

### P2 · PRs ≤ 500 lines diff (target)
Larger PRs require explicit sign-off from two reviewers and a description of why the change cannot be split.

### P3 · No `--no-verify` commits
Pre-commit hooks exist for a reason. Bypassing them is a process violation.

### P4 · No force-push to shared branches
Only personal branches may be force-pushed.

### P5 · Migrations land alone
A migration PR contains only the migration + safety test + (if needed) data backfill. No code changes that depend on the new schema in the same PR — that is a separate follow-up PR after the migration deploys.

### P6 · Feature flags expire
Every flag has a sunset date in metadata. After sunset, a quarterly cleanup workflow opens an issue. Past two quarters, the flag is removed (and the dead branch with it).

### P7 · Postmortems are blameless and published
Every Sev1/Sev2 incident produces a postmortem under `docs/postmortems/` within 5 business days. Action items have owners and SLAs.

---

## 4 · On-call Guardrails

### O1 · Runbook required
A new failure mode requires a runbook in `docs/runbooks/` referenced from the alert payload. Alert without runbook = paged engineer files a P1 to add one.

### O2 · Alert hygiene
An alert that fires > 3× without action being required is tuned or deleted within the same week.

### O3 · Error budget freeze
SLO error budget burn > 50% in a quarter freezes feature work in the affected context until budget recovers.

### O4 · Chaos drills are real
Skipping or postponing a scheduled chaos drill requires architecture-WG sign-off.

---

## 5 · Security Guardrails

### S1 · Secrets never in source
Pre-commit + CI grep gate. Discovered secret = immediate rotation + postmortem.

### S2 · Dependencies scanned weekly
`pip-audit` + `npm audit`. Critical CVEs trigger an immediate PR.

### S3 · Tenancy isolation regression test runs every PR
Failure blocks merge. No exceptions, no `xfail`.

### S4 · RLS coverage = 100%
A CI test enumerates all user-data tables and asserts RLS enabled.

### S5 · No prod data in staging or local
Synthetic data only. Anonymized exports require Data Protection sign-off.

---

## 6 · Cost Guardrails

### $1 · Pre-flight projection
Before model dispatch, `model_router` projects cost; reject (402) if projected > org remaining budget.

### $2 · Per-org daily cap enforced
Source: `org_billing.daily_budget_cents`. Cascade promotion (Flash → Pro) is gated on remaining budget.

### $3 · Cost regression alert
Cost per generation rolling-7d > 1.5× baseline → alert. Investigate before next deploy.

### $4 · Customer-facing cost dashboard
Per-customer dashboards must be implementable from `ai_invocations` alone. Adding a new model call without writing to that table is a P0.

---

## 7 · Documentation Guardrails

### D1 · Blueprint stays canonical
The first place to look for an architectural answer is the blueprint. If the answer is wrong or missing, fix it there.

### D2 · No new top-level `*_PLAN.md`
Architecture content goes in `docs/architecture/`. Operational content goes in `docs/runbooks/`. Project-management content goes in GitHub issues / project board. Repo root is for code, not prose.

### D3 · Code comments justify, not describe
A comment explains *why*, not *what*. The *what* is the code. Out-of-date comments are deleted on sight.

### D4 · README is for contributors
Marketing copy lives on the website. README links to:
- Quickstart
- Blueprint
- Contributing
- License
