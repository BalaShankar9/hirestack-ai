# HireStack AI — Production Upgrade Plan

**Created:** 2026-04-16  
**Status:** Actively executing  

---

## Priority Levels

| Level | Definition |
|-------|-----------|
| **P0** | Must fix before production — blocking or critical security issue |
| **P1** | High-value improvement — should ship in next sprint |
| **P2** | Important but non-blocking — ship when capacity allows |

---

## P0 — Blockers

### P0-1: Rate limiting not firing on 15 route files

- **Problem:** `@router.post` decorator was placed before `@limiter.limit` — Python decorator order means limiter never wrapped the handler
- **Files:** `backend/app/api/routes/{ats,career,salary,learning,documents,review,api_keys,evidence_mapper,job_sync,feedback,variants,resume,generate/...}.py`
- **Risk:** CRITICAL — all rate limits silently bypassed, enabling DoS and brute force
- **Status:** ✅ Fixed in session 2 (2026-04-16)

### P0-2: CI test failures silently swallowed

- **Problem:** `npm test ... || true` and `|| echo "No tests yet"` let broken tests pass CI
- **Files:** `.github/workflows/ci.yml`
- **Risk:** HIGH — regressions ship undetected
- **Status:** ✅ Fixed in this audit (2026-04-16)

### P0-3: `/api/frontend-errors` unprotected

- **Problem:** No rate limiting on error collection endpoint — anyone could flood logs
- **Files:** `backend/main.py`
- **Risk:** MEDIUM — log flooding, disk exhaustion
- **Status:** ✅ Fixed — rate limited at 30/min per IP

### P0-4: `robots.ts` exposes all dashboard paths

- **Problem:** Used Next.js route group notation `/(dashboard)/` as the disallow path — this is invisible in actual URLs, so all dashboard routes were allowed to crawlers
- **Files:** `frontend/src/app/robots.ts`
- **Risk:** MEDIUM — PII in dashboard URLs indexed by search engines
- **Status:** ✅ Fixed — explicit URL path list used

---

## P1 — High-Value Improvements

### P1-1: Frontend env validation at startup

- **Problem:** No check that required `NEXT_PUBLIC_*` vars are set — app silently fails to auth without clear error message
- **Files:** `frontend/src/lib/env-validation.ts` (new), `frontend/src/components/providers.tsx`
- **Risk:** Developer experience + support burden
- **Status:** ✅ Implemented (2026-04-16)

### P1-2: Global request timeout middleware

- **Problem:** No HTTP-level timeout on the backend — a hung AI call or DB query blocks the connection slot indefinitely
- **Files:** `backend/app/core/tracing.py`, `backend/main.py`
- **Risk:** MEDIUM — resource exhaustion under load
- **Status:** ✅ Implemented (120 s safety net)

### P1-3: CI ESLint gate missing

- **Problem:** CI ran typecheck and build but no ESLint — style/quality issues shipped silently
- **Files:** `.github/workflows/ci.yml`
- **Risk:** Code quality regression
- **Status:** ✅ Fixed — `npm run lint -- --max-warnings=0` added

### P1-4: No Dependabot for automated security patches

- **Problem:** Dependencies updated only manually — security patches can be missed
- **Files:** `.github/dependabot.yml` (new)
- **Risk:** Known CVE exposure over time
- **Status:** ✅ Created — weekly schedule for npm, pip, GitHub Actions

### P1-5: DB migration validation was a no-op

- **Problem:** CI loop iterated over `.sql` files but body was empty — any broken migration passed
- **Files:** `.github/workflows/ci.yml`
- **Risk:** Schema drift, broken deployments
- **Status:** ✅ Fixed — now checks non-empty, timestamp ordering, and SQL keyword presence

### P1-6: mobile login "Back to home" missing

- **Problem:** Mobile users on login page had no way back to home without the browser back button
- **Files:** `frontend/src/app/login/page.tsx`
- **Status:** ✅ Fixed in session 2

### P1-7: Achievement system + streak engagement hooks

- **Problem:** No daily retention mechanics to drive user habit formation
- **Status:** ✅ Implemented — `useAchievements` hook, `AchievementToast` with confetti, streak sidebar widget

---

## P2 — Improvements

### P2-1: Bundle size tracking

- **Problem:** No bundle analyzer configured — can't see if a dependency doubles the bundle
- **Recommendation:** Add `@next/bundle-analyzer` as dev dependency, add `analyze` script
- **Priority:** P2 — add before next major dependency upgrade

### P2-2: CORS origins in env var

- **Problem:** `cors_origins` list is hardcoded in `config.py` including Railway subdomain
- **Recommendation:** Move to `CORS_ORIGINS` env var in production, keep defaults for dev
- **Priority:** P2 — low risk but operationally cleaner

### P2-3: JWT secret rotation runbook

- **Problem:** No documented process for rotating the Supabase JWT secret
- **Recommendation:** Add to `docs/runbooks/jwt-rotation.md`
- **Priority:** P2

### P2-4: File upload magic-bytes validation

- **Problem:** File uploads check MIME type from extension but not magic bytes
- **Recommendation:** Add `python-magic` and verify first 512 bytes match declared type
- **Priority:** P2 — acceptable risk with current file parsing approach

### P2-5: Staging environment

- **Problem:** No staging — every PR merge goes straight to production
- **Recommendation:** Railway preview environments or Netlify preview deploys
- **Priority:** P2

### P2-6: `success_response()` consistency

- **Problem:** Some routes return raw dicts, others use `success_response()` wrapper
- **Recommendation:** Add mypy/ruff rule to enforce consistent response shape
- **Priority:** P2

### P2-7: `not-found.tsx` dark mode polish

- **Problem:** `not-found.tsx` uses hardcoded gradient that doesn't respect dark mode toggle
- **Priority:** P2 — cosmetic

---

## Execution Order

1. ✅ P0-1 Rate limiting (done)
2. ✅ P0-2 CI test failures (done)
3. ✅ P0-3 `/frontend-errors` rate limit (done)
4. ✅ P0-4 robots.ts (done)
5. ✅ P1-1 Env validation (done)
6. ✅ P1-2 Request timeout (done)
7. ✅ P1-3 ESLint CI gate (done)
8. ✅ P1-4 Dependabot (done)
9. ✅ P1-5 DB migration validation (done)
10. ⬜ P2-1 Bundle analyzer
11. ⬜ P2-2 CORS env var
12. ⬜ P2-3 JWT runbook
13. ⬜ P2-4 Magic bytes
14. ⬜ P2-5 Staging
