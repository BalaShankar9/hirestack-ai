---
title: Release Readiness
last_synced: 2026-05-08
watch_paths:
  - CHANGELOG.md
  - RELEASE.md
  - .github/workflows
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#20-stage-a-exit-criteria
  - /memories/repo (m*-pr*-shipped notes)
update_when:
  - a P0 / P1 lands or moves status
  - a Stage A criterion shifts (added, removed, achieved)
  - the deferred list changes
---

# Release Readiness

> The single source of truth for "are we ready to call Stage A done?"
> Answer: not yet — 7 of 7 P0s shipped, 14 of 15 P1s shipped, 1 P1
> deferred. The remaining work is documentation tightening and the
> deferred items' explicit acceptance.

---

## TL;DR — 10 lines

1. **Stage A target:** product is reliable enough for paying Pro / Team
   customers in a single cell, single region.
2. **P0s (must-have):** 7 / 7 SHIPPED.
3. **P1s (should-have):** 14 / 15 SHIPPED. 1 DEFERRED with rationale.
4. **Quality gates:** all 11 required CI gates green on `main`.
5. **Runbooks:** 6 of 6 page-level alerts have runbooks.
6. **Cost telemetry:** per-org daily cap enforced (P0-4); per-call
   accounting in `ai_invocations` (P1-8).
7. **Tenancy:** 64 of 64 multi-tenant tables have RLS; isolation test
   green nightly.
8. **Pipeline durability:** per-stage activities (P1-1); SSE resume
   (P1-3); event archive (P1-12).
9. **Provider failover:** Anthropic provider live behind `ff_anthropic_
   provider` (P1-4 — m7-pr28); failover test stable (m12-pr12).
10. **Remaining for Stage A close:** TD-4 lockfile, TD-10 namespace
    cleanup, TD-3 metrics instrumentor, P1-13 explicit deferral note.

---

## P0 status (must-have for any production use)

| ID | Item | Status | Anchor |
|---|---|---|---|
| P0-1 | Tenancy isolation test (RLS contract) | SHIPPED | `tests/security/test_tenancy_isolation.py` |
| P0-2 | SSRF defense — `safe_fetch` IP-pinning + bandwidth budget | SHIPPED | `ai_engine/tools/fetch.py` |
| P0-3 | Idempotency middleware + 24h TTL sweep | SHIPPED | `backend/app/api/middleware/idempotency.py` |
| P0-4 | Per-org daily cost cap (`usage_guard`) | SHIPPED | `backend/app/services/usage_guard.py` (m12-pr08) |
| P0-5 | Tool registry + capability tokens | SHIPPED — m7-pr29 | `ai_engine/registry/` |
| P0-6 | Idempotency replay test green in CI | SHIPPED | `tests/middleware/test_idempotency.py` |
| P0-7 | RLS regression test added to required gates | SHIPPED | `.github/workflows/tenancy-isolation.yml` |

---

## P1 status (should-have for a clean Stage A)

| ID | Item | Status | Anchor |
|---|---|---|---|
| P1-1 | Per-stage Temporal activities | SHIPPED — m8-pr32 | `backend/app/temporal/workflows/generation.py` |
| P1-2 | DLQ enrollment + admin replay endpoint | SHIPPED — m7-pr27c | `backend/app/queue/dlq.py` |
| P1-3 | SSE resume via `Last-Event-ID` | SHIPPED — m9-pr34/35 | `backend/app/api/routes/generate/streaming.py` |
| P1-4 | Anthropic provider failover behind feature flag | SHIPPED — m7-pr28 | `ai_engine/model_router.py` |
| P1-5 | Strict event schema validation | SHIPPED — m7-pr31 | `packages/events/schema/v1` |
| P1-6 | AI invocations partition rotation | SHIPPED — m7-pr27a | `pg_partman` job |
| P1-7 | In-process fallback gated by feature flag (off in prod) | SHIPPED — m7-pr27b | `config/feature_flags.yaml` |
| P1-8 | `ai_invocations` flight recorder + cost rollup | SHIPPED — m7-pr30 | `ai_engine/observability/invocations.py` |
| P1-9 | Event schema deprecation window (dual-emit) | SHIPPED — m11-pr37 | `packages/events/schema/` |
| P1-10 | Coverage gate ≥ 75% backend | SHIPPED — m12-pr02 | `.github/workflows/coverage.yml` |
| P1-11 | Triage 9 baseline test failures | SHIPPED | per-test commits in m12-pr05 |
| P1-12 | Event archive workflow | SHIPPED | `backend/app/temporal/workflows/event_archive.py` |
| P1-13 | Per-region observability split | **DEFERRED** | rationale below |
| P1-14 | Bootstrap registry on cold start | SHIPPED — m7-pr27d | `ai_engine/registry/bootstrap.py` |
| P1-15 | Staging mirror compose | SHIPPED | `infra/staging-mirror.compose.yml` |

---

## P1-13 — Per-region observability (deferred)

**Decision:** defer to Stage B. Stage A is single-cell, single-region;
per-region split adds dashboard surface that has nobody to consume it.

**What's still required:** every span attribute MUST already include
`cell_id` even though it currently has one value. This is checked by a
contract test so when we cell-split, the data is already shaped right.

Tracked as TD-9 (Stage B blocker).

---

## Stage A exit criteria checklist

| Criterion | Status |
|---|---|
| All P0 items shipped | ✅ |
| All P1 items shipped or explicitly deferred | ✅ (P1-13 deferred) |
| All 11 required CI gates green on `main` | ✅ |
| Tenancy isolation green nightly for 14 days | ✅ |
| Provider failover drilled (Gemini breaker → Anthropic) | ✅ (m12-pr12 test stable) |
| Per-org daily cost cap exercised in load test | ✅ |
| `ai_invocations` rollup matches Stripe within 1% (sample) | ⏳ — manual reconciliation cadence not yet set |
| 6 / 6 page-level alerts have runbooks | ✅ |
| `infra/staging-mirror.compose.yml` works on a clean clone | ✅ |
| TD-4 lockfile in place | ❌ |
| TD-10 dual-namespace shim removed | ❌ |
| TD-3 metrics instrumentor swap | ❌ |
| `/context` documentation system in place | ⏳ — m12-pr13 |
| ADRs for every load-bearing decision | ✅ (40 ADRs) |
| Backup + DR runbook drilled in last 90 days | ❌ |

---

## Definition of "shipped"

A P0/P1 item is SHIPPED only when:

1. Code merged to `main`.
2. Tests merged with the code, exercising the contract — not just the
   happy path.
3. Telemetry emitted (metric / span attribute / event).
4. Runbook (if alert-bearing).
5. Memory note `/memories/repo/m<N>-pr<NN>-shipped.md`.
6. CHANGELOG entry.

If any of those is missing, the item is IN PROGRESS, not SHIPPED.

---

## What's in flight (not yet PRs)

- **TD-1 split** — scheduled post m12-pr13.
- **TD-4 lockfile** — first PR after m12-pr13.
- **Reconciliation cadence** — Stripe vs `ai_invocations` rollup;
  monthly manual job, automated to weekly Stage B.
- **DR drill** — quarterly schedule; first one in next sprint.

---

## What's "explicitly NOT in Stage A"

- Multi-region routing (Stage B).
- Mobile native parity (mobile/ has the scaffold; Pro tier feature).
- Public API (Stage B; needs API key model + per-key rate limit).
- BYOK (bring-your-own-key for Gemini / Anthropic) — Enterprise feature
  for Stage B+.
- ATS submission automation — explicitly out of scope (BUSINESS_LOGIC
  §explicitly NOT in scope).

---

## Release cadence

- **Backend:** continuous. Each merge to `main` deploys.
- **Frontend:** continuous. Each merge to `main` deploys to Netlify.
- **Database migrations:** applied during deploy via Supabase CLI;
  always backwards-compatible (additive); destructive changes are 2-PR
  with deprecation window.
- **Tagged releases:** monthly cut for the changelog; not tied to
  deploys.

---

## Sign-off

Stage A close requires sign-off from:

- Engineering lead (CI gates, runbooks, TD checklist).
- Product lead (P0/P1 status, deferrals).
- Security lead (RLS contract, SSRF, capability tokens).

Sign-off recorded in `RELEASE.md`.
