# S1 — Platform Core — Audit

**Date**: 2026-04-28
**Scope**: `backend/main.py`, `backend/app/__init__.py`, `backend/app/core/*`, `backend/app/api/deps.py`, `backend/app/api/response.py`
**Total LOC in scope**: 3,241 (12 files)

---

## 1. File Inventory

| File | LOC | Verdict |
|------|----:|---------|
| [backend/main.py](../../backend/main.py) | 801 | **Oversized** — needs split (lifespan, health, metrics, errors) |
| [backend/app/__init__.py](../../backend/app/__init__.py) | 1 | OK |
| [backend/app/core/database.py](../../backend/app/core/database.py) | 793 | **Oversized** — five concerns in one file |
| [backend/app/core/metrics.py](../../backend/app/core/metrics.py) | 321 | OK |
| [backend/app/core/queue.py](../../backend/app/core/queue.py) | 241 | OK |
| [backend/app/core/tracing.py](../../backend/app/core/tracing.py) | 239 | OK (4 middleware classes — could split) |
| [backend/app/core/circuit_breaker.py](../../backend/app/core/circuit_breaker.py) | 200 | OK — clean |
| [backend/app/api/deps.py](../../backend/app/api/deps.py) | 175 | OK |
| [backend/app/core/security.py](../../backend/app/core/security.py) | 129 | OK |
| [backend/app/core/feature_flags.py](../../backend/app/core/feature_flags.py) | 123 | Excellent — keep as the model |
| [backend/app/core/config.py](../../backend/app/core/config.py) | 118 | OK |
| [backend/app/core/sanitize.py](../../backend/app/core/sanitize.py) | 88 | OK |
| [backend/app/api/response.py](../../backend/app/api/response.py) | 12 | **Underused** — only `success_response`, no error envelope |

---

## 2. Dependency Vulnerabilities (pip-audit)

29 known CVEs in 6 packages. Highest priority:

| Package | Current | Fix | Severity |
|---------|---------|-----|----------|
| `pyjwt` | 2.9.0 | **2.12.0** | **CRITICAL** — CVE-2026-32597 (auth path) |
| `starlette` | 0.46.2 | **0.49.1** | **HIGH** — CVE-2025-54121 + CVE-2025-62727 (HTTP layer) |
| `pypdf` | 5.0.1 | **6.10.2** | High — 23 CVEs in PDF parsing (used in resume ingest) |
| `pillow` | 11.0.0 | **12.2.0** | Medium — image decode |
| `markdown` | 3.7 | **3.8.1** | Medium |
| `pytest` | 8.3.5 | **9.0.3** | Low (dev-only) |

**Action**: All 6 require version bumps in `backend/requirements.txt`. PyJWT and Starlette are non-negotiable production-blockers.

---

## 3. Architecture Gaps

### G1 — `database.py` mixes five concerns (793 LOC)
Currently bundles:
1. Supabase client init/teardown (~50 LOC)
2. JWT verification (sync + async, with token cache) (~200 LOC)
3. `TABLES` map (~80 LOC)
4. `SupabaseDB` CRUD wrapper (~250 LOC)
5. Redis cache client + helpers (~200 LOC)

**Recommendation**: split into `app/core/db/{client.py, tables.py, dao.py}`, `app/core/auth/jwt.py`, `app/core/cache/redis.py`. Keep `database.py` as a thin re-export shim for back-compat (services import `get_db`, `TABLES`, `verify_token_async`).

### G2 — `main.py` lifespan is 200+ LOC of side-effects
Lifespan currently does: Sentry init, Redis warmup, queue group, Supabase validate, AI key validate, recover inflight jobs, hydrate quality observations, seed catalog, cleanup orphans, runtime check, periodic cleanup task, JobWatchdog start, SIGTERM handler.

**Recommendation**: extract to `app/core/lifespan.py` with `startup_steps: list[StartupStep]`. Each step has `name`, `required_in_prod: bool`, `timeout_s`, `run()`. Lifespan loops, logs each, fails fast on required-in-prod. Makes adding/removing steps a one-liner and unit-testable.

### G3 — `/health` endpoint is 90 LOC inline in main.py
Couples liveness, readiness, and diagnostics. `/livez` already exists (good). But `/health` returns 503 when AI key missing in prod even if DB is fine — that's not always right (background jobs can still drain).

**Recommendation**: extract to `app/api/routes/health.py` with three endpoints:
- `GET /livez` — process alive (already exists, keep)
- `GET /healthz/ready` — DB + Redis reachable (block traffic if not)
- `GET /health` — full diagnostic dump (debug only / authed)

### G4 — Response envelope inconsistency
`response.py` is only 12 LOC and only defines `success_response`. Routes mix three patterns: bare dicts, `success_response(...)`, and ad-hoc `{"detail": ...}` for errors. No `error_response` helper. No correlation of `request_id` into the body for non-500 errors.

**Recommendation**: add `error_response(message, code, *, request_id, errors=None)` and document the envelope.

### G5 — `os.getenv` usage outside `config.py`
Found in 6 files (15 occurrences):
- [backend/app/core/database.py](../../backend/app/core/database.py) — `SUPABASE_HTTP_RETRIES`, `SUPABASE_HTTP_RETRY_BASE_S`, `SUPABASE_HTTP_RETRY_MAX_S`
- [backend/app/core/queue.py](../../backend/app/core/queue.py) — queue tuning vars
- [backend/app/core/security.py](../../backend/app/core/security.py) — `REDIS_URL`, `RATE_LIMIT_REQUESTS`
- [backend/app/core/feature_flags.py](../../backend/app/core/feature_flags.py) — by design (per-flag env reads). **Keep.**
- [backend/app/api/routes/billing.py](../../backend/app/api/routes/billing.py) — env reads for plan codes
- [backend/app/services/billing.py](../../backend/app/services/billing.py) — Stripe key, price IDs

Drift is **bounded**, not pervasive (the previous audit overstated this). Move the 9 non-feature-flag reads into `Settings`. Stripe price IDs especially should be a typed `dict[Plan, str]` on `Settings`.

### G6 — JWT verification: cache key derivation
`_TokenCache._key` uses SHA-256 of the token, truncated to 32 hex chars (128 bits). That's fine cryptographically but the cache has **no negative caching** — a flood of bad tokens hits the remote `/auth/v1/user` every time (DoS amplifier). Add a 60s negative cache for known-invalid tokens.

### G7 — Circuit-breaker registry is **not** wrapped around Supabase or Stripe
Only AI providers have breakers. A Supabase outage will hammer it on every request. Stripe network blips become 5xx storms.

**Recommendation**: introduce breakers `supabase` and `stripe`, wire into `SupabaseDB._run` (around the executor) and `BillingService` HTTP calls.

### G8 — No structured logging of auth failures
`get_current_user` logs `auth_failed` with truncated error but doesn't include `request_id` (relies on global processor) and doesn't differentiate between cache miss / signature fail / expired / network. Hard to diagnose auth incidents from logs alone.

### G9 — Test coverage gaps in scope
Scanning `backend/tests/`:
- ✅ `test_health.py` — health, security headers
- ✅ `test_observability_w3.py` — metrics
- ✅ `test_resilience_w8.py` — circuit-breaker state encoding
- ✅ `test_perf_optimizations.py` — phase metrics
- ❌ **No `test_config.py`** — settings validators, prod-fail-fast paths untested
- ❌ **No `test_database.py`** — `SupabaseDB._is_transient_error`, retry/backoff, `_TokenCache` LRU, table-missing-error detection all untested
- ❌ **No `test_security.py`** — `get_user_or_ip`, `SecurityHeadersMiddleware` HSTS branch untested
- ❌ **No `test_deps.py`** — `validate_uuid`, `get_current_user` happy/sad paths, 503 on `AuthServiceUnavailable`, 403 on disabled user untested
- ❌ **No `test_tracing.py`** — `RequestIDMiddleware` honour-incoming, length-cap, generated; `MaxBodySizeMiddleware` 413 path; `TimeoutMiddleware` 504 path untested
- ❌ **No `test_circuit_breaker.py`** — state machine transitions, half-open probe untested directly
- ❌ **No `test_feature_flags.py`** — truthy/falsy/unknown token semantics untested
- ❌ **No `test_sanitize.py`** — `sanitize_html` XSS payloads untested
- ❌ **No `test_response.py`** — envelope shape untested

**Production-Ready bar #1 (Coverage)**: 8 missing test modules in S1 alone.

---

## 4. Security Findings

| ID | Finding | Severity |
|----|---------|----------|
| S-1 | PyJWT 2.9.0 has CVE-2026-32597 — JWT verification path | **CRITICAL** |
| S-2 | Starlette 0.46.2 has CVE-2025-54121 + CVE-2025-62727 — HTTP layer | **HIGH** |
| S-3 | No negative cache → bad token DoS amplifies remote auth calls | Medium |
| S-4 | No circuit breaker on Supabase or Stripe → cascading failures | Medium |
| S-5 | `/health` exposes `model_health`, `circuit_breakers`, `metrics`, `queue` if `DEBUG=true` or `ENVIRONMENT != production` — easy to misconfigure in staging | Low |
| S-6 | CSP is `script-src 'self'` only — good, but no `report-uri` for monitoring | Low |
| S-7 | `MaxBodySizeMiddleware` exempts `/api/upload` with no per-route limit | Low |

---

## 5. Performance / Scale Gaps

| ID | Finding |
|----|---------|
| P-1 | Token cache holds 256 entries process-local; no shared cache across workers → token reverification on every worker LB hop. |
| P-2 | `SupabaseDB._lock` serializes ALL DB ops to one at a time per process — that is the **single biggest perf risk in S1**. The lock predates connection pooling discussion; with httpx pooled clients it's not needed. Verify and remove. |
| P-3 | `get_redis()` uses `socket_connect_timeout=2, socket_timeout=2` — fine for cache, but `r.ping()` on init is synchronous and blocks startup if Redis is wedged on its connect. |
| P-4 | No connection pool tuning documented; supabase-py defaults apply. |
| P-5 | `SecurityHeadersMiddleware` recomputes the headers list per request — micro, but cache the bytes. |

---

## 6. Documentation Gaps

- No ADR for: settings/config strategy, JWT verification fast-path, circuit breaker policy, retry semantics, `/health` vs `/livez` split.
- No runbook for: rotating SUPABASE_JWT_SECRET, enabling/disabling feature flags, draining a deploy.

---

## 7. Audit Verdict

**Status**: **Not production-ready.** Failing 4 of 7 production-ready bar items:
- ❌ Coverage (8 missing test modules)
- ❌ Resilience (no breaker on Supabase/Stripe; no negative auth cache)
- ⚠️ Security (PyJWT + Starlette CVEs)
- ⚠️ Performance (`SupabaseDB._lock` global serialization)
- ✅ Observability (metrics + structured logs in place)
- ❌ Docs (no ADRs, no runbooks)
- ❌ Release gate (no staging — owned by S10 but blocks S1 sign-off)

---

## 8. Fix Plan (ranked, ≤500 LOC each)

| # | Fix | Risk | Wins |
|---|-----|------|------|
| F1 | Bump `pyjwt`, `starlette`, `pypdf`, `pillow`, `markdown`, `pytest` to safe versions in `backend/requirements.txt` | Low (semver-compatible bumps) | Closes 29 CVEs |
| F2 | Add `test_config.py`, `test_feature_flags.py`, `test_sanitize.py` — pure-function tests, no I/O | Low | Closes 3 of 8 coverage gaps |
| F3 | Add `test_circuit_breaker.py` — state machine transitions, half-open probe | Low | Closes resilience coverage gap |
| F4 | Add `test_tracing.py`, `test_security.py`, `test_deps.py` — middleware + auth boundary | Medium | Closes 3 coverage gaps; high-value |
| F5 | Add negative auth cache (60s) in `_TokenCache`; export `_token_cache` for tests | Low | Closes S-3 |
| F6 | Add `error_response()` helper to `response.py` and adopt in 1 reference route | Low | Sets the pattern for S4/S7 |
| F7 | Move `SUPABASE_HTTP_RETRIES/*` env reads into `Settings` | Low | Closes G5 partially |
| F8 | Verify and remove `SupabaseDB._lock` global serialization (with benchmark) | Medium | Major perf win |
| F9 | Add `supabase` and `stripe` circuit breakers wired into the call sites | Medium | Closes S-4 |
| F10 | Split `database.py` into `app/core/db/`, `app/core/auth/jwt.py`, `app/core/cache/redis.py` (re-export shim) | Medium | Reduces blast radius |
| F11 | Extract `main.py` lifespan into `app/core/lifespan.py` with declarative steps | Medium | Testable startup |
| F12 | Extract `/health` family into `app/api/routes/health.py`; add `/healthz/ready` | Low | Cleaner main.py |

**Sequencing**: F1 → F2 → F3 → F4 → F5 → F6 → F7 (Fix step done). F8–F12 belong in Upgrade/Harden steps.

After every PR: backend unit suite stays green & under 15s.
