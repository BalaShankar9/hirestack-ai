# S8 Frontend Web — Audit & Risk Inventory

**Squad:** S8 — Frontend Web (Next.js 14 app under `frontend/`)
**Date:** 2026-04-21
**Owner:** Platform / Frontend
**Status:** F0 OPEN

## Scope

`frontend/src/` — Next.js 14 app router, Tailwind, Radix UI,
Supabase client. ~18k LOC, 300+ files, 24 vitest test files
(197 tests, baseline 6.74s).

## Surface inventory

| Area                           | LOC      | Existing tests              |
|--------------------------------|----------|-----------------------------|
| `src/lib/firestore/ops.ts`     | 2497     | `firestore-ops.test.ts` (large) |
| `src/lib/export.ts`            | 753      | `export.test.ts`             |
| `src/lib/api.ts`               | 626      | `api-client.test.ts` (10)   |
| `src/lib/ai-service.ts`        | 238      | none                        |
| `src/lib/sanitize.ts`          | 155      | **NONE — XSS critical**     |
| `src/lib/document-universe.ts` | 146      | none                        |
| `src/lib/env-validation.ts`    | 120      | none                        |
| `src/lib/error-reporting.ts`   |  93      | none                        |
| `src/hooks/use-*`              | 570      | partial (intel-prefetch)    |
| Page components                | (large)  | per-page smoke tests exist  |

Largest pages (deferred — page decomposition is post-S8 work):

| File                                                | LOC  |
|-----------------------------------------------------|------|
| `app/(dashboard)/applications/[id]/page.tsx`        | 2836 |
| `app/(dashboard)/nexus/page.tsx`                    | 1760 |
| `app/(dashboard)/new/page.tsx`                      | 1289 |
| `app/page.tsx`                                      | 1093 |
| `app/(dashboard)/dashboard/page.tsx`                |  988 |

## Risk inventory

| ID | Surface                       | Severity | Why                                                                 |
|----|-------------------------------|----------|---------------------------------------------------------------------|
| R1 | `lib/sanitize.ts`             | HIGH     | XSS firewall (escapeHtml, sanitizeUrl, sanitizeHtml, file allowlist) — zero tests |
| R2 | `lib/env-validation.ts`       | HIGH     | Startup contract for Supabase + API URLs; silent breakage on misconfig |
| R3 | `lib/document-universe.ts`    | MEDIUM   | Module → slot mapping; a regression here renders blank dashboards   |
| R4 | `lib/error-reporting.ts`      | MEDIUM   | Sentry envelope; PII leakage risk if shape drifts                   |
| R5 | `lib/api.ts` extras           | LOW-MED  | `uploadFile` retry path + `sanitizeErrorDetail` not yet pinned       |
| R6 | `hooks/use-download-gate.ts`  | MEDIUM   | Plan-gate + entitlement contract                                    |

## Out of scope (intentional, deferred to later workstreams)

- Decomposition of `applications/[id]/page.tsx` (2836 LOC) and
  `nexus/page.tsx` (1760 LOC) — physical extraction is a refactor
  and belongs to a Frontend-UX squad.
- A11y audit of every dashboard page (CCWG-Sec/Design).
- Lighthouse > 90 verification (S10 Infra & Deploy / SRE).
- React Query caching strategy review (CCWG-Perf).
- Code-splitting per route (CCWG-Perf).

## Fix queue

- **F1**: pin `lib/sanitize.ts` — XSS-critical primitives.
- **F2**: pin `lib/env-validation.ts` — env contract.
- **F3**: pin `lib/document-universe.ts` — module/slot mapping.
- **F4**: pin `lib/api.ts` `uploadFile` + `sanitizeErrorDetail`
  (extends existing `api-client.test.ts`).
- **F5**: pin `lib/error-reporting.ts` envelope shape.
- **F6**: ADR-0010 frontend contract surface + S8 sign-off.

## Verification gate (every PR)

```
cd frontend && npx vitest run --reporter=dot
```

Suite must stay GREEN. Latency budget: < 30s on this hardware
(currently 6.74s; ample headroom).
