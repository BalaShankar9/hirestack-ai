# HireStack AI — Production Audit Journal

**Date:** 2026-04-16  
**Auditor:** Principal Engineer (Copilot Agent)  
**Scope:** Full platform — frontend, backend, AI engine, CI/CD, infra, docs  

---

## 1. Codebase Map

| Layer | Technology | Entry Point |
|-------|-----------|-------------|
| Frontend | Next.js 14 App Router, TypeScript 5 strict, Tailwind | `frontend/src/app/layout.tsx` |
| Backend | FastAPI 0.109+, Python 3.11, Pydantic 2 | `backend/main.py` |
| AI Engine | Google Gemini 2.5 Pro (HS256 JWT auth, circuit breaker) | `ai_engine/agents/orchestrator.py` |
| Database | Supabase (PostgreSQL + RLS), 26 ordered migrations | `supabase/migrations/` |
| Auth | Supabase Auth (JWT HS256, email/Google/GitHub) | `backend/app/core/database.py` |
| Observability | structlog (JSON), Sentry, Prometheus `/metrics` | `backend/main.py` |
| Cache | Redis Streams (job queue + TTL cache), in-memory fallback | `backend/app/core/queue.py` |
| CI/CD | GitHub Actions (3 jobs: frontend, backend, security) | `.github/workflows/ci.yml` |

---

## 2. Inspection Findings by Category

### A. Architecture — GOOD
- Clean layering: route → service → database throughout the backend
- AI engine is fully isolated from FastAPI routes (import at call sites, not globally)
- Frontend uses a central `api.ts` (20 KB) for all backend communication
- Supabase RLS enforces user isolation at the DB layer — backend service role only used for admin operations
- Circuit breaker on AI provider calls prevents cascading failures

**Smell detected:** `app-shell.tsx` was 26 KB — large component managing navigation + auth state + streak widget. Acceptable given it's the only place, but worth splitting if it grows further.

### B. Type Safety — GOOD
- TypeScript `strict: true` enforced
- Pydantic v2 on backend with `field_validator`
- Shared types in `frontend/src/types/index.ts` (636 lines)
- `any` usage in some service files — acceptable, mostly in AI chain responses

**Gap detected:** No Zod validation on frontend form inputs — using only HTML `required`/`pattern`. Low risk given Supabase Auth handles credentials, but worth adding to the custom profile/evidence forms.

### C. Security — MOSTLY GOOD
**Fixed in this audit:**
- `/api/frontend-errors` endpoint had no rate limiting — could be used to flood logs. Now rate-limited at 30/min.
- `robots.ts` used `/(dashboard)/` which is a Next.js route group prefix (invisible in URLs) — all dashboard pages were effectively de-cloaked. Fixed to use actual URL paths.
- Decorator order bug across 15 route files (`@router` before `@limiter`) meant rate limiting never fired on those endpoints. Fixed in previous session.

**Remaining:**
- CORS `cors_origins` list includes Railway subdomain hardcoded. Should move to `CORS_ORIGINS` env var for production flexibility.
- JWT secret rotation policy not documented. Add to runbook.
- File upload uses server-side MIME check but not magic-bytes validation.

### D. Database — GOOD
- 26 ordered migration files with meaningful names
- RLS policies on all user tables
- Indexes on `user_id`, `created_at` (composite where needed)
- Foreign key constraints with cascade delete
- No `ON DELETE NO ACTION` footguns detected

**Gap:** No DB health check in `/health` for Supabase edge case where client initializes but PostgREST is down. Currently checks `get_supabase()` is not None — should add a lightweight `count=1` probe query.

### E. API Quality — GOOD
- Rate limiting on all endpoints (fixed in this audit)
- Request validation via Pydantic
- UUID validation via `validate_uuid()` dep
- Request ID tracing via `X-Request-ID`
- Structured JSON logging with request correlation
- `success_response()` helper exists in `app/api/response.py` but inconsistently used

**Gap:** Some routes return raw dicts instead of `success_response()` wrapper. Inconsistent for API consumers.

### F. Frontend UX — GOOD
- Loading skeleton states on all major pages
- Error boundaries at root and section level
- Empty states with clear CTAs
- Auth-gated routes redirect to login with `?redirect=` param
- Double-submit protection on forms via `disabled` state during loading

**Fixed:** Autosave indicator on JD textarea, regeneration confirmation dialog, mobile "Back to home" link.

### G. Performance — GOOD
- Static asset immutable cache (31536000s) in `next.config.js`
- `next/image` for all images
- Standalone output mode for Docker
- API rewrites to avoid CORS preflight on same-origin

**Gap:** No `next-bundle-analyzer` configured — can't see bundle size trends. Add as dev dependency.

### H. Testing — GOOD
- 22 frontend test files (Vitest + Testing Library + Playwright)
- 50+ backend test files (pytest + pytest-asyncio)
- E2E tests via Playwright

**Fixed in this audit:** CI was swallowing test failures (`|| true`, `|| echo "No tests yet"`). Tests now properly gate the CI pipeline.

### I. Observability — EXCELLENT
- Sentry error monitoring (frontend + backend)
- structlog JSON structured logging
- Request ID correlation across all logs
- Prometheus-compatible `/metrics` endpoint
- Circuit breaker state exposed in `/health`
- Pipeline run metrics (p50/p95 latency, success rate, error counts)
- Frontend error batching to backend collector

### J. CI/CD — IMPROVED
**Fixed in this audit:**
- Added `concurrency:` group to cancel stale runs
- Added ESLint gate with `--max-warnings=0`
- Fixed silent test failures — tests now properly fail CI
- Added DB migration order validation (timestamp ordering)
- Added non-empty file check for migrations
- Added `.env.example` existence check
- Added Dependabot for npm, pip, and GitHub Actions

**Remaining:**
- No staging environment — PR deploys go straight to production
- No smoke test post-deployment
- No rollback script

### K. Future Scale — GOOD FOUNDATIONS
- Redis Streams for async job queue (horizontally scalable)
- Worker process separate from API process
- Circuit breaker prevents AI provider overload
- Supabase handles horizontal DB scaling via pooler
- Rate limiting per IP (slowapi + Redis)

---

## 3. Risk Register

| Risk | Severity | Status |
|------|----------|--------|
| Rate limiting not firing (decorator order) | CRITICAL | ✅ Fixed |
| Test failures swallowed in CI | HIGH | ✅ Fixed |
| `/api/frontend-errors` unprotected | MEDIUM | ✅ Fixed |
| `robots.txt` exposes dashboard URLs | MEDIUM | ✅ Fixed |
| No env validation on frontend startup | MEDIUM | ✅ Fixed |
| CORS origins hardcoded in config | LOW | ⚠️ Documented |
| No staging environment | LOW | ⚠️ Documented |
| JWT secret rotation undocumented | LOW | ⚠️ Documented |
| File upload magic-bytes check missing | LOW | ⚠️ Documented |
| Bundle size not tracked | LOW | ⚠️ Documented |

---

## 4. Audit Summary

**Architecture quality:** Production-grade  
**Security posture:** Strong with known gaps documented  
**Observability:** Excellent  
**Test coverage:** Good (unit + integration + E2E)  
**CI/CD safety:** Significantly improved  
**UX resilience:** Very good  

See `docs/release-readiness-report.md` for final verdict.
