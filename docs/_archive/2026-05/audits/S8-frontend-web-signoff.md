# S8 — Frontend Web — Sign-off

**Date:** 2026-04-21
**Lead:** autonomous loop
**Status:** ✅ COMPLETE
**Reference:** [`0010-frontend-web-contract-surface.md`](../adrs/0010-frontend-web-contract-surface.md)

## Scope delivered

| Risk | Surface | Action | Tests added |
| --- | --- | --- | --- |
| R1 | `lib/sanitize.ts` (XSS critical, 155 LOC, 0 tests) | Pinned escape/url/html/file allowlist | 57 |
| R2 | `lib/env-validation.ts` (startup contract) | Pinned required/optional rules + memoisation | 18 |
| R3 | `lib/document-universe.ts` (doc registry) | Pinned shape, key uniqueness, group ordering | 24 |
| R5 | `lib/api.ts` (uploadFile + sanitizeErrorDetail + Retry-After) | Pinned multipart upload, traceback scrubbing, retry timing | 19 |
| R4 | `lib/error-reporting.ts` (Sentry envelope) | Pinned envelope shape, queue cap, 5 s timer, global handler | 20 |

**Total new tests:** 138.
**Frontend suite:** 197 → 335 passed (+138). Duration 6.74 s →
7.72 s. Well below the 30 s budget.

## Out of scope (deferred with rationale)

- **R6 — `hooks/use-download-gate.ts` (plan-gate logic):** depends
  on Supabase profile shape that overlaps with a future Billing
  workstream; deferred to that squad to avoid premature contract
  capture.
- **Page decomposition:** `applications/[id]/page.tsx` (2836 LOC),
  `nexus/page.tsx` (1760), `new/page.tsx` (1289), `app/page.tsx`
  (1093), `dashboard/page.tsx` (988). Owned by a future
  Frontend-UX squad — a refactor not a contract pin.
- **A11y audit, Lighthouse > 90, React Query review, code-split per
  route:** owned by CCWG-Sec, S10/S11, and CCWG-Perf respectively.

## Commits (LOCAL on `main`)

| SHA | Title |
| --- | --- |
| `c6e4049` | S8-F0: frontend web audit + risk register |
| `5824b64` | S8-F1: pin lib/sanitize.ts XSS + upload allowlist (R1) |
| `ff33d4a` | S8-F2: pin lib/env-validation.ts contract (R2) |
| `86a8a91` | S8-F3: pin lib/document-universe.ts shape (R3) |
| `a8c51fb` | S8-F4: pin api.uploadFile + sanitizeErrorDetail (R5) |
| `a2394cd` | S8-F5: pin lib/error-reporting.ts behaviour (R4) |
| _next_ | S8-F6: ADR-0010 + sign-off |

All commits remain LOCAL until the S10 staging gate.

## Verification gate

- `cd frontend && npx vitest run --reporter=dot` → 335 passed in
  7.72 s.
- Backend suite untouched (1715 / 8.12 s baseline still holds).

## Next

**S9 — Mobile (Android Kotlin).** Begin with F0 audit of
`mobile/android/` Kotlin tree.
