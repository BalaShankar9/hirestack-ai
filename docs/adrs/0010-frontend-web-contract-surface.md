# ADR-0010 — Frontend Web Contract Surface

**Date:** 2026-04-21
**Status:** Accepted
**Squad:** S8 — Frontend Web

## Context

The Next.js 14 frontend (`frontend/`, ~18k LOC, 300+ files) is the
primary user surface for HireStack AI. It includes the Supabase
client, a typed REST client, the document-universe registry, an XSS
sanitiser, an env-validation shim, and a client-side error reporter.

S7 closed the backend domain services. S8 closes the frontend
contract surface — the low-level libs every page depends on — by
pinning their behaviour with vitest.

Page-level decomposition (e.g. the 2836-LOC
`applications/[id]/page.tsx`) is explicitly OUT of scope for S8 and
is deferred to a future Frontend-UX squad: this ADR pins what cannot
silently regress, not what should be refactored for ergonomics.

## Decision

The following frontend contracts are now pinned and **must not
change without an updated ADR + test update**.

### `lib/sanitize.ts` (R1, XSS-critical)

- `escapeHtml`: encodes `&<>"'` (single quote as `&#39;`); `&` first
  so existing entities are double-escaped; returns `""` for
  `null`/`undefined`; coerces non-strings via `String(...)`.
- `sanitizeUrl`: allowlist `http:`/`https:`/`mailto:`; root-relative
  paths permitted; protocol-relative `//evil.com` BLOCKED;
  `javascript:`/`data:`/`file:`/`vbscript:` BLOCKED; trims whitespace
  before parsing.
- `sanitizeHtml`:
  - **Client path (DOMParser):** strips `<script|iframe|object|embed|
    form|link|meta|base>`; unwraps unknown safe tags keeping
    children; removes inline `on*` handlers; strips `javascript:`
    from `href`/`src` even with whitespace obfuscation; preserves
    documented safe tag/attr set including
    `data-section`/`data-module`/`role`/`aria-*`.
  - **Server path (no `window`):** regex strip of dangerous tags +
    `on*` attributes + literal `javascript:` URI prefix.
- `ALLOWED_STORAGE_BUCKETS`: exactly `{"uploads"}`.
- `MAX_FILE_SIZE_BYTES`: exactly 25 MiB. `isAllowedFileSize` rejects
  `0` and negatives.
- `isAllowedFileExtension`: case-insensitive; uses LAST dot;
  allowlist documented.

### `lib/env-validation.ts` (R2)

- `validateEnv()` short-circuits to `{valid:true,errors:[],warnings:[]}`
  on the SSR path.
- Required: `NEXT_PUBLIC_SUPABASE_URL` (must start with `https://`),
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` (must be > 20 chars).
- Optional: `NEXT_PUBLIC_API_URL` — missing or wrong-scheme produces
  a warning, never an error.
- `checkEnvOnce()` is fully memoised; logs to `console.error` on
  errors; logs to `console.warn` on warnings only when
  `NODE_ENV !== "production"`; SSR no-op.

### `lib/document-universe.ts` (R3)

- `DOCUMENT_UNIVERSE` ≥ 50 entries; keys globally unique and
  snake_case `[a-z0-9_]+`.
- `group ∈ {recommended, professional, executive, academic,
  compliance, technical, creative}`.
- `recommended === true ⇔ group === "recommended"` (bidirectional).
- `RECOMMENDED_KEYS` includes the canonical 11-doc set; every key
  exists in `DOCUMENT_UNIVERSE`.
- `GROUP_META` orders are unique and contiguous from 0;
  `recommended` sorts first (order 0).
- `TAILORED_UNIVERSE` and `BENCHMARK_UNIVERSE` are identity-equal to
  `DOCUMENT_UNIVERSE` (deprecation aliases).
- `findUniverseDoc` is case-sensitive; ignores deprecated `_tier` arg.
- `mergeWithUniverse` preserves universe order; on duplicate
  `docType` keeps the FIRST occurrence (matches "newest-first input").

### `lib/api.ts` (R5)

- `MAX_RETRIES = 3`; `NON_RETRYABLE = {400, 401, 402, 403, 404, 409,
  422}`.
- `request()`: retries on 5xx and network `TypeError`; respects
  `Retry-After` numeric seconds; falls back to `attempt * 2000` ms
  when header is non-numeric or missing.
- `uploadFile`: multipart `FormData` with file under `"file"` key;
  does NOT set `Content-Type` (lets browser supply boundary); auth
  header from `setToken()`; per-call token argument overrides;
  `additionalData` entries appended; same retry policy as `request()`.
- `sanitizeErrorDetail`:
  - 5xx detail containing `Traceback`/`File "`/`line ` → "Something
    went wrong on our end. Please try again."
  - Same patterns on 4xx → "Request failed (`status`)".
  - Detail > 300 chars truncated to 300 (4xx) or replaced with
    generic message (5xx).
  - Missing detail → "HTTP error! status: `<code>`".
  - Clean short detail preserved verbatim.

### `lib/error-reporting.ts` (R4)

- POST URL: `/api/backend/frontend-errors`. Payload:
  `{errors: ErrorReport[]}`. `keepalive: true`.
- Envelope fields: `message`, `stack` (≤ 2000), `componentStack`
  (≤ 1000), `url`, `timestamp` (ISO-8601), `userAgent`.
- `MAX_QUEUE = 20`; overflow silently dropped; FIRST 20 retained.
- `FLUSH_MS = 5000`; timer fires at exactly 5000 ms; enqueues during
  the window do NOT reset it; new timer starts after each flush.
- `fetch` failures are swallowed.
- `installGlobalErrorHandler()`:
  - SSR no-op.
  - `'error'` event → `event.error if Error else event.message`.
  - `'unhandledrejection'` → coerces non-Error reason via
    `String()`; `null`/`undefined` reason → "Unhandled promise
    rejection".
  - `visibilitychange → hidden` triggers immediate `flush()`.

## Out of scope (deferred)

- Decomposition of oversized pages (`applications/[id]/page.tsx`
  2836 LOC, `nexus/page.tsx` 1760 LOC, `new/page.tsx` 1289 LOC,
  `app/page.tsx` 1093 LOC, `dashboard/page.tsx` 988 LOC) — owned by
  a future Frontend-UX squad.
- A11y audit of dashboard pages — owned by CCWG-Sec/Design.
- Lighthouse > 90 verification — owned by S10 Infra & Deploy / S11.
- React Query caching strategy review — owned by CCWG-Perf.
- Code-splitting per route — owned by CCWG-Perf.
- `firestore/ops.ts` (2497 LOC) deeper coverage — already has a
  large dedicated `firestore-ops.test.ts` (524 LOC) that pins the
  primary contracts; further coverage is a maintenance task.

## Consequences

- **Positive:** XSS firewall, env contract, document registry, REST
  client, and error pipeline are all pinned by deterministic vitest
  cases. A regression flips the suite RED at `npx vitest run`.
- **Positive:** Frontend baseline grew from 197 tests / 6.74 s to
  335 tests / 7.72 s — well within the 30 s frontend latency budget.
- **Positive:** No production code was changed; this is contract
  capture only.
- **Negative:** Tests are coupled to current implementation
  invariants. Intentional behaviour changes require both an ADR
  amendment and test updates.
