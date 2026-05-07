# S1 Platform Core — production-ready sign-off

Date: 2026-04-21
Squad: Platform Core (S1)
Status: **GREEN**

## 7-point production-ready bar

| # | Criterion                                            | Status | Evidence |
|---|------------------------------------------------------|--------|----------|
| 1 | Unit suite green and <15 s                           | ✅     | 1221 passed in 6.01 s after F11. |
| 2 | No critical CVEs in pinned deps                      | ✅     | F1 (a4e2976) bumped FastAPI 0.128.2, Starlette 0.50.0, PyJWT 2.12+; `pip-audit` clean for HIGH/CRITICAL. |
| 3 | All env vars centralised via `Settings`              | ✅     | F7 (a7a34f3) removed the last stray `os.getenv` calls; 7 tests pin Settings as the single source. |
| 4 | All external deps wrapped in circuit breakers        | ✅     | Supabase + Stripe wrapped (F9 / f6058c5). AI providers were already wrapped pre-S1. ADR-0001. |
| 5 | Structured logs include `request_id`                 | ✅     | `RequestIDMiddleware` + `request_id_var` ContextVar pinned by 16 tests in F4 (9890e24). |
| 6 | Dedicated `/healthz/ready` endpoint                  | ✅     | F11 (b381c13) — 200 iff Supabase reachable; Redis optional (in-mem fallback). ADR-0003. |
| 7 | Lifespan startup checks fail loud, not silent        | ✅     | `init_supabase` raises on bad URL/key; AI provider key checked at boot via existing lifespan; degraded `/health` reflects either failure. |

## Fixes shipped

| ID  | Commit  | Title                                              |
|-----|---------|----------------------------------------------------|
| F1  | a4e2976 | CVE bumps (FastAPI / Starlette / PyJWT)            |
| F2  | 70b2d6c | Settings test coverage (12 tests)                  |
| F3  | —       | Skipped (already covered)                          |
| F4  | 9890e24 | Tracing test coverage (16 tests)                   |
| F5  | 9b63f59 | Negative auth cache + 11 tests                     |
| F6  | 278cdf6 | `error_response` helper + 14 tests                 |
| F7  | a7a34f3 | Stray getenv → Settings + 7 tests                  |
| F8  | b0cf974 | Remove `SupabaseDB._lock` + 2 tests                |
| F9  | f6058c5 | Supabase + Stripe breakers + 3 tests               |
| F10 | 6d68b9c | Extract cache layer + 4 tests                      |
| F11 | b381c13 | Extract /health family + add /healthz/ready + 5 tests |
| F12 | (this)  | ADRs + runbooks + S1 sign-off                      |

## Documentation produced

- `docs/adrs/0001-circuit-breakers-supabase-stripe.md`
- `docs/adrs/0002-cache-module-extraction.md`
- `docs/adrs/0003-health-vs-readiness-probes.md`
- `docs/runbooks/circuit-breaker-recovery.md`
- `docs/runbooks/cache-degraded-mode.md`
- `docs/audits/S1-platform-core.md` (the audit that drove F1–F12)

## Deferred items

These were explicitly scoped out of S1 to keep PRs ≤500 LOC. They
are **not** blockers for the staging deploy gate at P4-S10.

1. **Database/Auth/JWT split** — `app/core/database.py` is still
   756 LOC after F10. A future PR should move JWT verification into
   `app/core/auth/` and the back-compat Firestore aliases
   (`FirestoreDB = SupabaseDB`, `init_firebase`, etc.) into a
   shim module that can be deleted once `gap.py`, `job.py`, and
   `benchmark.py` are migrated.
2. **Lifespan extraction** — startup/shutdown logic is still inline
   in `main.py`. Tangles with Sentry init / structlog config; doing
   it standalone would have pushed F11 past budget.
3. **Cache hit-rate metric** — flagged in the Redis runbook. Add a
   counter so on-call can see hit-rate during a Redis outage.

## Next squad

P1-S2 (Data & Migrations) and P1-S3 (Pipeline Runtime) start in
parallel.
