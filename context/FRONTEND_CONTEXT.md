---
title: Frontend Context
last_synced: 2026-05-08
watch_paths:
  - frontend/src
  - frontend/package.json
  - frontend/next.config.js
  - frontend/playwright.config.ts
  - frontend/vitest.config.ts
  - frontend/tailwind.config.ts
canonical_sources:
  - frontend/package.json
  - frontend/src/lib/sseClient.ts
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#9-realtime
update_when:
  - a new (dashboard) route is added
  - the SSE client contract changes (Last-Event-ID, reconnect semantics)
  - the OpenAPI SDK regen target changes
  - a heavy dep (pdfjs-dist, html2pdf, mammoth) is added or removed
  - the routing model changes (App Router -> Pages, etc.)
---

# Frontend Context

> The frontend is a single Next.js 14 App Router app served from
> <https://hirestack.tech> via Netlify. The package manifest is the source
> of truth for dependencies; this file is the source of truth for **how
> they are used together**.

---

## TL;DR — 12 lines

1. **Next.js 14.1.0 + React 18.2.0 + TypeScript** with the **App Router**
   (no Pages directory).
2. **Tailwind + shadcn-style primitives + Radix UI** for the design system.
   Framer Motion 12.38 for transitions; no animation library beyond it.
3. **Server state lives in TanStack Query v5** (`@tanstack/react-query
   ^5.17`). Local UI state is React state/hooks. There is no Redux / Zustand
   / Jotai.
4. **REST is consumed via `openapi-fetch` + `openapi-typescript`-generated
   types,** rolled out file-by-file (strangler pattern from hand-written
   `lib/api/`). New code uses the SDK; legacy hand-written clients still
   exist and are migrated as touched.
5. **SSE is the only push channel.** WebSockets are NOT used. The wrapped
   client lives at [`frontend/src/lib/sseClient.ts`](../frontend/src/lib/sseClient.ts).
   **Native `EventSource` is forbidden** (ADR-0039 Proposed) because it
   does not support `Last-Event-ID` reliably across rolling deploys.
6. **Mission-Control UI** (`frontend/src/components/pipeline/`) renders the
   six-agent stream as collapsible per-agent panels with live token output,
   timing badges, and an aggregate progress bar.
7. **Authentication uses Supabase JS** (`@supabase/supabase-js ^2.49.10`)
   with cookies for SSR-safe sessions
   (`@supabase/auth-helpers-nextjs ^0.10`).
8. **Heavy dependencies are dynamically imported per route** to keep the
   initial bundle tight: `pdfjs-dist@5.4.530`, `html2pdf.js`, `html2canvas`,
   `mammoth` (DOCX), `jszip`, `marked`. Static imports of these in shared
   layout components is forbidden.
9. **Editor is TipTap 2.1.16** (Bold, BulletList, OrderedList, Link, Lists,
   Paragraph, Underline). Used in cover-letter and personal-statement
   surfaces.
10. **Testing:** vitest 2.1.9 (unit) + Testing Library + Playwright 1.58
    (E2E across chromium/firefox/webkit). E2E specs live in `frontend/e2e/`.
11. **Hosting:** Netlify with `netlify.toml` at repo root. Build via Next
    standalone output. Preview deploys per PR (Netlify built-in).
12. **Bundle budget:** none enforced yet (open item — Lighthouse CI gate
    planned for end of Stage A; blueprint §25.3).

---

## App Router structure

```
frontend/src/app/
├── layout.tsx                — root layout (TanStack Query provider, theme, supabase)
├── page.tsx                  — landing
├── (auth)/
│   ├── login/page.tsx
│   ├── register/page.tsx
│   └── reset/page.tsx
├── (dashboard)/              — authenticated surface (group route, no segment)
│   ├── layout.tsx            — sidebar + topbar + auth guard
│   ├── dashboard/page.tsx    — home
│   ├── new/page.tsx          — start a generation
│   ├── applications/         — list, detail, actions
│   ├── ats-scanner/
│   ├── builder/              — manual CV/cover builder
│   ├── candidates/           — agency Kanban
│   ├── career/, career-analytics/
│   ├── consultant/
│   ├── evidence/             — evidence ledger viewer
│   ├── gaps/, insights/
│   ├── interview/            — interview simulator
│   ├── job-board/, knowledge/
│   ├── learning/             — learning streaks
│   ├── ppt/                  — slide-deck generator
│   ├── salary/, skills/
│   ├── tracked-companies/
│   ├── ab-lab/, batch/, benchmark/
│   ├── nexus/, export/
│   ├── upload/               — resume / JD ingestion
│   ├── api-keys/             — Stage B
│   ├── assignments/
│   └── settings/
└── api/                      — Next.js route handlers (proxy / auth helpers)
```

Every `(dashboard)/*` route shares the auth guard in
`(dashboard)/layout.tsx`. Unauthenticated requests redirect to `/login`.

---

## Streaming UI: Mission Control

The flagship UX is the live six-agent pipeline:

```
+-------------------------------------------------------+
| Generation #abc123     [progress ===========> 78%]    |
+-------------------------------------------------------+
| > Atlas       (resume parser)         3.4s   green   |
|   - skills extracted: 24                              |
|   - experience years: 7.2                             |
| v Cipher      (gap analyzer)          2.1s   running |
|   ▌ "Analysing fit against benchmark..."             |
|   ▌ "Identifying 3 critical gaps..."                  |
| > Quill       (drafter)               --     pending |
| > Forge       (portfolio)             --     pending |
| > Sentinel    (quality gate)          --     pending |
| > Nova        (assembly)              --     pending |
+-------------------------------------------------------+
```

Wiring (in order):

1. The user POSTs to `/api/generate/jobs`. Backend returns `{job_id,
   sse_url}`.
2. The page mounts a `<MissionControl jobId=...>` component
   (`components/pipeline/MissionControl.tsx`).
3. `MissionControl` opens an SSE connection via `sseClient.ts` to
   `/api/generate/agentic-stream/{job_id}`.
4. Backend streams `stage.started`, `stage.token` (when token streaming is
   enabled), `stage.completed`, `pipeline.completed` events.
5. The component dispatches each event into a per-agent reducer
   (`components/pipeline/usePipelineState.ts`) which produces the panel
   state above.
6. On disconnect, the client sends `Last-Event-ID` (read from `X-Session-ID`
   header on the original GET) on reconnect; backend replays missed events
   from `AgenticEventEmitter.get_events_after()`.
7. On `pipeline.completed` the component navigates to the result page.

**Forbidden patterns:**

- `new EventSource(...)` anywhere. Use `openSseStream()` from
  `lib/sseClient.ts`.
- Polling the job status as a substitute for SSE.
- Long-polling `setInterval`-based progress checks.

---

## Data fetching pattern

```ts
// canonical: TanStack Query + openapi-fetch
import { createClient } from "openapi-fetch";
import { useQuery } from "@tanstack/react-query";
import type { paths } from "@/lib/api/generated";

const api = createClient<paths>({ baseUrl: process.env.NEXT_PUBLIC_API_BASE });

export function useApplications() {
  return useQuery({
    queryKey: ["applications"],
    queryFn: async () => {
      const { data, error } = await api.GET("/applications");
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    staleTime: 30_000,
  });
}
```

Mutations use `useMutation` with optimistic updates only when the operation
is idempotent. The backend Idempotency-Key middleware handles deduplication
(`Idempotency-Key: <uuid>` on every POST/PATCH/DELETE).

The OpenAPI SDK is regenerated by `frontend/scripts/check-sdk-drift.ts`.
A CI gate (`openapi-drift`) fails the PR if the generated types are out of
sync with `backend/main.py /openapi.json`.

---

## Heavy dependencies (dynamic-imported)

| Package | Version | Where it's used | Why dynamic |
|---|---|---|---|
| `pdfjs-dist` | `5.4.530` | resume parsing preview | ~3 MB worker |
| `html2pdf.js` | `^0.12` | export to PDF | wraps html2canvas + jsPDF |
| `html2canvas` | `^1.4.1` | export, screenshot | DOM scrape |
| `mammoth` | `^1.10.0` | DOCX parsing | only on upload route |
| `jszip` | `^3.10` | zip pack export | only on export route |
| `framer-motion` | `^12.38` | Mission-Control transitions | imported per page |

Pattern:

```ts
const Heavy = dynamic(() => import("@/components/HeavyOnlyOnThisRoute"), {
  ssr: false,
  loading: () => <Skeleton />,
});
```

Adding any of these to a layout or `_app`-equivalent is a regression.

---

## Auth flow

1. User hits `/login`.
2. Supabase JS sign-in returns a session.
3. Cookies are set by `@supabase/auth-helpers-nextjs` so SSR can read them.
4. Subsequent requests carry the JWT in `Authorization: Bearer <token>`.
5. Backend `JWTAuthMiddleware` validates and sets `request.state.user`.
6. RLS in Postgres scopes every query to that user's `org_id`.

Server-side route handlers in `app/api/` use the same Supabase server
helpers; never re-implement auth in a Next API route.

---

## State and data layers (canonical paths)

| Concern | Library / file |
|---|---|
| Server state (REST) | TanStack Query v5 |
| Realtime push | `lib/sseClient.ts` (SSE only) |
| Auth client | `lib/supabaseClient.ts` (browser), `@supabase/auth-helpers-nextjs` (server) |
| Forms | React Hook Form + zod |
| Theming | Tailwind + CSS variables in `styles/globals.css` |
| Icons | `lucide-react` |
| Toasts | `sonner` |
| Charts | `recharts` |
| Date / time | `date-fns` |

The folder `frontend/src/lib/firestore/` is a **misleading name**: it holds
Supabase data-access helpers, not Firebase / Firestore code. A Firestore
detour was reverted very early in the project (see
[`docs/PROJECT_JOURNAL.md`](../docs/PROJECT_JOURNAL.md)). Renaming is open
work; treat the path as `lib/supabaseData/`.

---

## Testing

| Layer | Tool | Where |
|---|---|---|
| Unit | vitest 2.1.9 + Testing Library | `frontend/src/**/__tests__/*` |
| Component | vitest + Testing Library | colocated `*.test.tsx` |
| E2E | Playwright 1.58 (chromium/firefox/webkit) | `frontend/e2e/*.spec.ts` |
| Visual | none enforced (open) | future Lighthouse CI |
| Coverage | v8 via vitest | `frontend/coverage/` (not gated yet) |

Run: `cd frontend && npm run test` (unit) or `npm run e2e` (Playwright).
Playwright reuses the dev server unless `CI=1`.

---

## Build and deploy

- `next build` produces a standalone server in `output/` (gitignored).
- `netlify.toml` declares the build command and Next adapter version.
- Preview URL per PR (Netlify built-in).
- Production URL: <https://hirestack.tech>.
- Env vars (set in Netlify): `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE`,
  `NEXT_PUBLIC_SENTRY_DSN`, plus build-only secrets in
  `.env.production` (managed by Netlify, not in repo).

---

## Accessibility & i18n

- Radix primitives ship with ARIA out of the box; do not regress them by
  swapping in custom keyboard handlers.
- No i18n framework today. Strings live in components. When we i18n, we will
  pick `next-intl` (decision pending; not an ADR yet).

---

## What "good frontend" looks like in this repo

When reviewing a frontend PR, check:

- [ ] Uses TanStack Query for any new server data (no `useEffect` + fetch).
- [ ] Uses generated `openapi-fetch` types if the backend route exists in
      OpenAPI.
- [ ] No `new EventSource` anywhere; uses `lib/sseClient.ts`.
- [ ] Heavy deps imported via `dynamic()` if route-specific.
- [ ] Form validation via React Hook Form + zod.
- [ ] Strings in components (no inline lorem-ipsum).
- [ ] Accessible by default (Radix primitive or `<button>` not `<div onClick>`).
- [ ] Vitest test for non-trivial logic; Playwright spec if user-visible flow.
- [ ] No new top-level dependency without checking bundle impact.
