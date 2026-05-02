# HireStack Master Integration Plan — "The Career-Ops Absorption + 1-Click Assist + Beyond"

> Single source of truth for what we're building, why, in what order, with
> what schema deltas, what gates, and what we explicitly will NOT do.
> Supersedes the execution sequencing in the three sibling docs.
> Date: 2026-05-02. Owner: BalaShankar. Format: ship-by-ship.

## 0. Mission framing

> **HireStack finds 5 high-fit jobs a day, packages each one with a
> tailored CV + cover letter + interview prep + ghost check + comp
> read while you sleep, and you apply with one click in the morning.
> No spam. No ToS violation. No hallucinated experience.**

That sentence is the spec. Every feature below either advances it or
gets cut.

---

## 1. The complete integration list (29 items, grouped, prioritized)

### Tier 0 — Foundation prerequisites (must ship first, unblocks everything)

| # | Item | Effort | Unblocks |
|---|------|--------|----------|
| F1 | Status taxonomy refactor: add `responded`/`discarded`/`skip` | 1d | F2, A2, A3, B2 |
| F2 | Stable 8-archetype classifier (LLM single-shot, deterministic labels) | 2d | A2, A4 |
| F3 | Liveness classifier service (multi-language regex tables) | 2d | A1, V1 |

### Tier A — Daily-engagement loops (DAU drivers)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| A1 | Cadence engine (`/api/cadence/today`) + `<CadenceToday />` panel | 3d | "Open this every morning" |
| A2 | Pattern Insights (`/api/insights/patterns`) + `/dashboard/insights` | 4d | Proprietary moat |
| A3 | Morning brief email (Postmark/Resend, 7am user-tz cron) | 3d | Reactivation channel |
| A4 | "What's New" panel + post-deploy migration CTAs | 1d | Touch-point per deploy |

### Tier B — Discovery + auto-prep (Layer 1 of 1-click assist)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| B1 | Portal scanner: Greenhouse/Ashby/Lever/Workday/SmartRecruiters/BambooHR direct APIs | 5d | Zero-token; cron'd; dedup against `job_scan_history` |
| B2 | `tracked_companies` schema + UI for adding/managing | 1d | Powers B1 |
| B3 | Auto-prep on hit: scanner → score → if ≥ user threshold, enqueue `generation_jobs` for full report+CV+letter | 2d | The "while you sleep" promise |
| B4 | Email-alert ingester: parse LinkedIn / Indeed / Welcome-to-the-Jungle alert emails → scan queue | 3d | Capture passive job seekers |
| B5 | "Ready to apply" inbox view in dashboard (5 cards waiting in the morning) | 2d | The morning-rendezvous UI |

### Tier C — Interview + content moats

| # | Item | Effort | Notes |
|---|------|--------|-------|
| C1 | STAR+R column added to all interview-prep chains (one-line prompt change) | 0.5d | Free seniority-signal upgrade |
| C2 | Story Bank with pgvector semantic dedup (cosine ≥ 0.85) | 3d | Compounds across applications |
| C3 | Negotiation as named scenarios (`geo_pushback`, `competing_offer`, `downlevel_accept`, `sell_senior`, `first_offer`, `exploding_offer`) | 1d | Sharper salary feature |
| C4 | Voice-mode mock interview (browser Web Speech API → `interview_sessions`) | 1w | Differentiator vs Teal/Huntr |
| C5 | LaTeX/Overleaf CV export | 1d | Engineer/academic delight |
| C6 | Self-host Space Grotesk + DM Sans + Inter fonts | 0.5d | Removes Google Fonts dep |

### Tier D — 1-click assist Layer 2 (browser extension)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| D1 | MV3 browser extension scaffold (Chrome + Firefox) | 2d | Manifest, auth, basic content script |
| D2 | ATS adapters: Greenhouse, Lever, Ashby, Workday, SmartRecruiters | 4d | One adapter per ATS form schema |
| D3 | Inline ghost-job badge overlay on LinkedIn Jobs / Indeed listings | 3d | Viral screenshot moment |
| D4 | "Fill from HireStack" autofill (profile fields) + tailored CV attach + tailored cover letter paste | 3d | Stops at Submit |

### Tier E — Public utilities (viral SEO + lead funnel)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| E1 | Public ghost-check: `hirestack.ai/ghost-check` — paste URL → verdict, no login. Per-scan permalink at `/g/<hash>` | 5d | Viral SEO surface; OG image dynamic |
| E2 | Public share URL for every report: `hirestack.ai/r/<slug>` (private by default; one-click public) | 3d | Users become distribution |
| E3 | JD anti-pattern detector: paste a JD → flag ageist/gendered/unrealistic-stack language. Free for both candidates and employers. | 3d | Press cycle bait; recruiter-facing too |
| E4 | Resume ATS pre-flight: paste resume → score against generic ATS rules. No JD needed. | 2d | Top-of-funnel SEO |
| E5 | Anonymous community vouch: users mark jobs `ghosted_me / responded / hired_me` → community signal augments automated detector | 4d | Network effect on legitimacy DB |

### Tier F — Distribution surfaces (ride other platforms)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| F4 | `npx hirestack eval <url>` CLI (npm package, thin client) | 2d | Dev-tribe surface |
| F5 | MCP server `@hirestack/mcp` (Claude Desktop / Cursor) | 2d | Marketplace listing |
| F6 | Custom GPT in OpenAI store + Claude Skill | 2d | Free discovery channels |
| F7 | Zapier / Make.com / n8n integration | 2d each | More marketplaces |

### Tier G — Personalization + voice (long-tail moats)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| G1 | Self-rewriting prompts: per-user `prompt_overrides` JSONB → 200-token system patch applied to every chain | 3d | "It learned my voice" magic |
| G2 | Pipeline integrity admin dashboard (`/internal/integrity/scan`) | 2d | Operational hygiene |
| G3 | TUI-inspired filter UX retrofit on `/dashboard/candidates` Kanban: 6 tabs, 4 sorts, grouped/flat, inline status picker | 2d | Triage speed |

### Tier H — Network plays (the bigger games)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| H1 | Referral finder: surface 2nd-degree connections at target companies + draft intro to mutual connection (LinkedIn OAuth) | 1w | Dramatically increases response rate |
| H2 | Public recruiter-facing profile: "open to" tag system; recruiters search HireStack instead of LinkedIn | 2w | Reverses the power dynamic |
| H3 | Comp-data aggregator: anonymized salary bands from scanned jobs → Levels.fyi-style comparison | 1w | Inbound SEO, recruiter signal |
| H4 | Calendar booking pages auto-prepped with company intel (Cal.com-style) | 1w | Closes the post-interview loop |

### Tier I — i18n (market expansion)

| # | Item | Effort | Notes |
|---|------|--------|-------|
| I1 | i18n tooling + first 3 locales: ES, PT-BR, DE | 1w | LLM-build-time translation |
| I2 | Locales 4–9: FR, KO, JA, HI, ZH-CN, ZH-TW (1d each) | 6d | Underserved-markets moat |

**Total scope: ~75 dev-days. Realistic: 8–10 weeks calendar at our velocity.**

---

## 2. Anti-list — what we explicitly will NOT build

| ❌ | Reason |
|---|---|
| **Auto-submit applications** | ToS violation on every major ATS, recruiter abuse, account-ban risk, brand poison |
| **Markdown-as-database** | Single-user pattern; we're SQL multi-tenant |
| **TSV transport** | We have generation_jobs queue |
| **Bubble Tea TUI** | Wrong form factor for SaaS |
| **Letter grades (A-F)** | Our 0-100 is more granular and machine-comparable |
| **Browser extension that auto-clicks Submit** | Same legal landmine as auto-submit |
| **Scraping LinkedIn job pages server-side** | Their ToS forbids; account ban risk |
| **Spamming recruiters via in-app messaging** | Career-suicide for users + bans us |
| **Spanish-default UI strings** in mode prompts | Career-ops's Spanish-first is awkward; we're English-first with full i18n |

---

## 3. Schema integration map (all migrations needed)

### 3.1 Applications status — additive CHECK extension

**File:** `supabase/migrations/20260503000000_application_status_taxonomy.sql`

```sql
BEGIN;

-- Drop the existing CHECK and replace with the extended set.
ALTER TABLE public.applications DROP CONSTRAINT IF EXISTS applications_status_check;
ALTER TABLE public.applications ADD CONSTRAINT applications_status_check
  CHECK (status IN (
    'draft', 'active', 'submitted', 'interview', 'offer',
    'rejected', 'withdrawn', 'archived',
    'responded', 'discarded', 'skip'        -- NEW
  ));

COMMENT ON COLUMN public.applications.status IS
  'draft|active|submitted (legacy ≈ applied)|responded (recruiter replied)|interview|offer|rejected|discarded (user closed for non-rejection)|skip (ghost/score<4, never apply)|withdrawn|archived';

COMMIT;
```

**Mapping for backwards compat:**
- `submitted` ↔ "applied" (display label only; no data move)
- `withdrawn` ↔ "discarded" (alias accepted, prefer discarded going forward)
- New flows write the new vocab; old data stays valid

**Service-layer enum:** `backend/app/models/application_status.py` (NEW) — single source of truth + alias map.

### 3.2 Tracked companies (powers B1, B2, B3)

```sql
CREATE TABLE IF NOT EXISTS public.tracked_companies (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  org_id          uuid NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  slug            text NOT NULL,
  display_name    text NOT NULL,
  ats_provider    text NOT NULL CHECK (ats_provider IN ('greenhouse','ashby','lever','workday','smartrecruiters','bamboohr','teamtailor')),
  ats_slug        text NOT NULL,
  careers_url     text NOT NULL,
  enabled         boolean NOT NULL DEFAULT true,
  last_scanned_at timestamptz NULL,
  scan_error      text NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, ats_provider, ats_slug)
);
ALTER TABLE public.tracked_companies ENABLE ROW LEVEL SECURITY;
-- Standard owner policies elided for brevity.
```

### 3.3 Application followups (powers A1, A3)

```sql
CREATE TABLE IF NOT EXISTS public.application_followups (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  uuid NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
  user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  channel         text NOT NULL CHECK (channel IN ('email','linkedin','phone','platform')),
  scheduled_for   timestamptz NOT NULL,
  sent_at         timestamptz NULL,
  draft_body      text NULL,
  replied_at      timestamptz NULL,
  cadence_rule    text NOT NULL,           -- e.g. 'applied_d7_first', 'responded_d1_first'
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_application_followups_user_due ON public.application_followups (user_id, scheduled_for) WHERE replied_at IS NULL AND sent_at IS NULL;
ALTER TABLE public.application_followups ENABLE ROW LEVEL SECURITY;
```

### 3.4 Story bank (powers C2)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.story_bank (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title               text NOT NULL,
  archetype_tag       text NULL,
  situation           text NOT NULL,
  task                text NOT NULL,
  action              text NOT NULL,
  result              text NOT NULL,
  reflection          text NULL,           -- the +R that flips perceived seniority
  evidence_app_ids    uuid[] DEFAULT '{}',
  reuse_count         int NOT NULL DEFAULT 0,
  last_used_at        timestamptz NULL,
  embedding           vector(1536),
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_story_bank_user ON public.story_bank (user_id, last_used_at DESC);
CREATE INDEX idx_story_bank_embedding ON public.story_bank USING ivfflat (embedding vector_cosine_ops);
ALTER TABLE public.story_bank ENABLE ROW LEVEL SECURITY;
```

### 3.5 Stable archetype tag on applications (powers F2, A2)

Store on `applications.meta.stable_archetype` — no schema change (meta column just shipped).

### 3.6 Public scan (powers E1)

```sql
CREATE TABLE IF NOT EXISTS public.public_scans (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url_canonical   text NOT NULL UNIQUE,
  url_hash        text NOT NULL UNIQUE,    -- short hash used in /g/<hash> permalink
  legitimacy_tier text NOT NULL CHECK (legitimacy_tier IN ('legitimate','caution','ghost','unknown')),
  reasoning       jsonb NOT NULL,
  http_status     int NULL,
  liveness        text NULL,
  age_days        int NULL,
  scan_count      int NOT NULL DEFAULT 1,
  first_scanned_at timestamptz NOT NULL DEFAULT now(),
  last_scanned_at  timestamptz NOT NULL DEFAULT now()
);
-- NO RLS needed — public read by design. Insert/update via service role only.
CREATE INDEX idx_public_scans_legit ON public.public_scans (legitimacy_tier, last_scanned_at DESC);
```

### 3.7 Community vouches (powers E5)

```sql
CREATE TABLE IF NOT EXISTS public.job_vouches (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url_canonical   text NOT NULL,
  user_id         uuid NULL REFERENCES auth.users(id) ON DELETE SET NULL,  -- nullable for anon
  vouch_type      text NOT NULL CHECK (vouch_type IN ('ghosted_me','responded','interviewed','hired_me','not_real')),
  applied_at      date NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (url_canonical, user_id, vouch_type)
);
ALTER TABLE public.job_vouches ENABLE ROW LEVEL SECURITY;
-- Anon users post via rate-limited public endpoint, NULL user_id.
```

### 3.8 Prompt overrides (powers G1)

Add column: `ALTER TABLE public.user_profile ADD COLUMN IF NOT EXISTS prompt_overrides jsonb DEFAULT '{}'::jsonb;`

---

## 4. Backend service surface (new modules)

| Module | Responsibility | Depends on |
|---|---|---|
| `backend/app/models/application_status.py` | Enum + alias map | — |
| `backend/app/services/liveness_classifier.py` | Pure function: classify URL fetch result | — |
| `backend/app/services/posting_legitimacy.py` | Combines liveness + scan_history + page-snapshot heuristics → tier | scan_history_service, liveness_classifier |
| `backend/app/services/portal_scanner.py` | Provider parsers + fan-out + dedup | url_canonicalizer, job_scan_history |
| `backend/app/services/cadence.py` | Compute today's followups buckets | — |
| `backend/app/services/pattern_insights.py` | Funnel + score scatter + archetype + blockers + recs | career_analytics |
| `backend/app/services/stable_archetype.py` | LLM single-shot 8-label classifier (cached per JD hash) | model_router |
| `backend/app/services/story_bank.py` | Extract STAR+R, semantic dedup, promote | embeddings, openai client |
| `backend/app/services/email_alert_ingester.py` | Parse forwarded LinkedIn/Indeed alert emails → scan queue | portal_scanner |
| `backend/app/services/integrity.py` | Health check functions | — |
| `backend/app/services/community_vouch.py` | Aggregate `job_vouches` into legitimacy signal | — |
| `backend/app/services/morning_brief.py` | Compose + send the daily email | cadence, portal_scanner, posting_legitimacy |

| Route | Method | Auth | Purpose |
|---|---|---|---|
| `/api/cadence/today` | GET | user | Cadence dashboard data |
| `/api/insights/patterns` | GET | user | Pattern insights data |
| `/api/companies/tracked` | GET/POST/DELETE | user | Manage tracked_companies |
| `/api/scan/run` | POST | user | Manual scan trigger |
| `/internal/scan/cron` | POST | service | Cron-driven fan-out |
| `/api/jobs/liveness` | POST | user | Body: `{url}` |
| `/api/jobs/legitimacy` | POST | user | Full posting legitimacy report |
| `/api/stories` | GET/POST/PUT/DELETE | user | Story bank CRUD |
| `/api/stories/extract-from/:application_id` | POST | user | Extract STAR+R from interview prep |
| `/api/insights/archetype` | POST | user | Body: `{jd_text}` → stable label |
| `/api/salary/negotiate` (extend) | POST | user | Add `scenario` enum param |
| `/api/changelog` | GET | user | Powers What's New panel |
| `/api/morning-brief/preview` | GET | user | Preview today's email |
| `/api/integrity/scan` | POST | admin | Operational health |
| `/api/share/report/:id` | GET | public | Public report share page (when toggled public) |
| `/g/:hash` | GET | public | Ghost-check permalink page |
| `/ghost-check` | POST | public+rate-limit | Anonymous URL submission |
| `/api/vouch` | POST | public+rate-limit | Community vouch submission |

---

## 5. Frontend integration map

| Page/Component | What changes |
|---|---|
| `/dashboard` (homepage) | Add `<CadenceToday />` as first widget; add `<ReadyToApply />` inbox card |
| `/dashboard/candidates` (Kanban) | New lanes: Responded, Discarded, Skip; TUI-inspired filter bar; inline status picker |
| `/dashboard/insights` (NEW) | Pattern insights page with 5 charts + recommendations |
| `/dashboard/discovery` (NEW) | Tracked companies list + scanner-found jobs feed |
| `/dashboard/stories` (NEW, under /nexus) | Story bank with rehearse mode |
| `/dashboard/settings/voice` (NEW) | Self-rewriting prompts UX |
| `/workspace/<app>` (existing) | Mount `<PostingLegitimacyPanel>` next to existing CandidateValidationPanel; "Generate share URL" CTA |
| `/workspace/<app>/interview` (existing) | Add Reflection column to STAR table; Story Bank insert UI |
| `/salary` (existing) | Scenario card-deck picker |
| `/ghost-check` (NEW, public) | Anonymous tool with OG-image-optimized result page |
| `/g/<hash>` (NEW, public) | Permalink result page (indexable) |
| `/r/<slug>` (NEW, public) | Public report share page (when user opts in) |
| `/jd-check` (NEW, public) | JD anti-pattern detector |
| `/resume-check` (NEW, public) | Resume ATS pre-flight |
| Top-nav | Add "Today" link as the new default landing |

---

## 6. Ship order with checkpoints (calendar)

**Each ship = one PR-shaped commit, tests pass, gate green, no rollback needed.**

### Week 1 — Foundation
| Day | Ship | Gate |
|---|---|---|
| Mon | F1 status-taxonomy migration + `ApplicationStatus` enum + alias map | DB migration applies idempotently; existing tests pass |
| Tue | F3 liveness_classifier service + unit tests (regex tables, all languages) | 100% branch coverage on classifier |
| Wed | E1.a `posting_legitimacy.py` service (combines liveness + scan_history) + unit tests | All scenarios covered |
| Thu | E1.b Public `/ghost-check` route + rate limiter + `/g/<hash>` permalink page | Anonymous request works; 5 req/min/IP |
| Fri | E1.c Dynamic OG image generator (Satori or @vercel/og equivalent) + landing | Manual visual QA |

### Week 2 — Daily loop
| Day | Ship | Gate |
|---|---|---|
| Mon | F2 stable_archetype service + caching by jd_hash | Single LLM call returns one of 8 labels deterministically |
| Tue | A1.a `cadence.py` service + `/api/cadence/today` route + unit tests | All 4 buckets correct vs fixtures |
| Wed | A1.b `<CadenceToday />` panel + integration test | Renders 4 buckets; "Generate draft" wires to existing follow_up_email gen |
| Thu | A3 morning brief email — Postmark/Resend integration + 7am cron | Test send works; user-tz respected |
| Fri | A4 What's New panel + `/api/changelog` | Reads from existing release notes |

### Week 3 — Insights moat + Posting Legitimacy panel
| Day | Ship | Gate |
|---|---|---|
| Mon | A2.a `pattern_insights.py` (funnel + scatter + archetype) + tests | Min-5-outcomes guard works |
| Tue | A2.b blocker frequency + recommendations engine + tests | Empty-state copy + min thresholds |
| Wed | A2.c `/dashboard/insights` page with Recharts | Visual QA |
| Thu | T1.A Posting Legitimacy panel mounted in IntelligencePanel; SSE meta plumbing for `posting_legitimacy` | Mirrors CandidateValidationPanel pattern |
| Fri | C1 STAR+R column added to all interview-prep prompts + chain tests | Reflection field appears in outputs |

### Week 4 — Discovery + Auto-prep
| Day | Ship | Gate |
|---|---|---|
| Mon-Tue | B2 + B1.a tracked_companies schema + UI; portal_scanner Greenhouse parser | E2E: add company → scan → results in pipeline |
| Wed | B1.b Ashby + Lever parsers + concurrency control | All 3 parsers verified against real APIs |
| Thu | B1.c Workday + SmartRecruiters + BambooHR + Teamtailor parsers | Long-tail providers covered |
| Fri | B3 auto-prep on hit (scanner → score ≥ threshold → enqueue generation) + B5 "Ready to apply" inbox view | E2E: morning email shows "5 ready" |

### Week 5 — Story Bank + Negotiation + Browser extension scaffold
| Day | Ship | Gate |
|---|---|---|
| Mon | C2.a story_bank schema + service (embed + dedup) + tests | Cosine ≥ 0.85 dedup works |
| Tue | C2.b Story extraction from interview-prep + `/dashboard/stories` UI | Stories accumulate; rehearse mode works |
| Wed | C3 negotiation scenarios + UI card-deck | 6 scenarios wired |
| Thu-Fri | D1 + D2.a browser extension MV3 scaffold + Greenhouse adapter | Local install works; autofill on Greenhouse |

### Week 6 — Browser extension finishing + LinkedIn ghost overlay
| Day | Ship | Gate |
|---|---|---|
| Mon | D2.b Lever + Ashby adapters | Autofill on both |
| Tue | D2.c Workday + SmartRecruiters adapters | Autofill works |
| Wed | D4 cover letter paste + tailored CV attach | Per-app document selection |
| Thu | D3 LinkedIn Jobs / Indeed inline ghost badge overlay | Badge shows next to listing titles |
| Fri | Chrome Web Store submission + Firefox Add-ons submission | Listed |

### Week 7 — Other public utilities + distribution surfaces
| Day | Ship | Gate |
|---|---|---|
| Mon | E2 public report share URLs + dynamic OG | Toggleable; OG renders |
| Tue | E3 JD anti-pattern detector public tool | Live |
| Wed | E4 resume ATS pre-flight public tool | Live |
| Thu | F4 `npx hirestack eval <url>` CLI + npm publish | Installable |
| Fri | F5 MCP server `@hirestack/mcp` | Claude Desktop tested |

### Week 8 — Personalization + community + i18n start
| Day | Ship | Gate |
|---|---|---|
| Mon | G1 prompt overrides + `/settings/voice` UX | Override applies to chains |
| Tue | E5 community vouch system + UI on /g/<hash> pages | Anonymous vouch works |
| Wed | C4 voice mock interview (Web Speech API) | E2E: speak → transcript → graded |
| Thu | C5 LaTeX export + C6 self-host fonts | LaTeX downloads compile |
| Fri | I1 i18n tooling + ES locale | Spanish UI renders |

### Weeks 9-10 — i18n rollout + B4 email ingester + G3 TUI UX retrofit + Tier H pilots
- I2 locales (PT-BR, DE, FR, KO, JA, HI, ZH-CN, ZH-TW)
- B4 email-alert ingester
- G3 Kanban TUI-inspired filter UX
- H3 comp aggregator (lower bar, no OAuth)
- F6/F7 Custom GPT, Claude Skill, Zapier (1 day each)

### Weeks 11+ — Tier H network plays
- H1 referral finder (LinkedIn OAuth)
- H2 public recruiter-facing profile
- H4 calendar booking

---

## 7. Hard rules — do not violate

These are inviolable. Every PR is checked against them.

1. **Never auto-submit applications.** Browser extension stops at Submit. Hard-coded.
2. **Never scrape ATS pages server-side at scale.** Use ATS public APIs only. Playwright only as last-resort fallback per-user.
3. **Never lie in legitimacy reports.** Present signals; let user decide. Never accuse a recruiter of dishonesty. Mandatory ethical-framing prompt section.
4. **Public utilities never require login.** Charging breaks the SEO loop.
5. **No data export from public scans without anonymization.** Personal info in JD body must be redacted before storage.
6. **Backwards-compatible migrations only.** Status taxonomy is additive — old values still valid forever.
7. **Hallucinated experience claims = ship blocker.** All CV claims must trace to nexus/cv evidence; no fabrication.
8. **Pre-existing baseline failures stay ignored** (RLS coverage, schema mirror, cascade-delete documentation tests — see session memory).
9. **Don't touch ATLAS provider env-flag gating** (`ATLAS_ARCHETYPES_ENABLED`).
10. **Don't rename `benchmark` module key** in `applications.modules` JSONB.
11. **Don't stage** anything in the NEVER-stage list (TODO.md, ai_engine/data/, frontend/src/features/, progress.txt, reference/, the existing untracked superpowers plan, untracked test files).

---

## 8. Rollback paths

| Ship | If broken, rollback by |
|---|---|
| Status taxonomy migration | Revert is impossible (CHECK constraint), but **no data writes the new values until services do** — so leave constraint in place, revert services. |
| Cadence engine | Feature-flag the panel + email; cron disabled |
| Portal scanner | Disable cron + hide UI behind flag |
| Browser extension | Unpublish from store; existing installs harmless (read-only) |
| Public ghost-check | Rate limit to 0 req/min via env var; route returns 503 |
| Pattern insights | Hide route; service is read-only so no harm |

---

## 9. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| ATS API rate limit | Medium | 10s timeout, exponential backoff, per-user concurrency cap |
| Embedding cost spike (Story Bank) | Low | Cache by content hash; ≥0.85 cosine threshold tight |
| Postmark/Resend deliverability | Medium | DKIM/SPF setup; test send to gmail/outlook/proton |
| LinkedIn detects extension overlay | Medium | Read-only DOM observer; no requests to LinkedIn from background |
| OpenAI / Anthropic outage during scan | Low | Auto-prep is best-effort; cadence/insights work offline |
| Public ghost-check legal complaint from a "ghosted" company | Low | Ethical framing in every report; user can request takedown via `/g/<hash>?takedown=...` |
| User confused by status vocab change | Medium | Onboarding modal + tooltip + alias accepted on writes |

---

## 10. Success metrics (gates after each tier)

- **Tier 0 ships** → No regression in existing tests (currently 35/35 ATLAS-FE green, backend gate green minus pre-existing baseline failures).
- **Tier A ships** → Daily-active users ≥ 30% of weekly-active. Morning brief open rate ≥ 35%.
- **Tier B ships** → Median user has ≥ 5 tracked companies. ≥ 1 auto-prepped report per user per day.
- **Tier C ships** → Story bank ≥ 5 stories per user after first 3 interview preps. Negotiation scenarios used in ≥ 40% of salary feature uses.
- **Tier D ships** → Browser extension installed by ≥ 25% of WAU.
- **Tier E ships** → Ghost-check tool gets ≥ 100 organic anonymous requests/day within 30 days. Indexed `/g/<hash>` pages = ≥ 1k after 90 days.
- **Tier F ships** → 1 marketplace listing per week of post-launch presence.

---

## 11. Today's first action

**Ship F1 status-taxonomy migration NOW** (1d work, 0 risk, unblocks 5 downstream items). Plan above. Beginning execution after this commit.

---

## 12. The relationship between the four docs

| Doc | What it does | When to read |
|---|---|---|
| `CAREER_OPS_GAP_ANALYSIS.md` | Feature parity matrix | Strategic context |
| `HIRESTACK_VIRALITY_PLAYBOOK.md` | Distribution wheels | Marketing/launch |
| `CAREER_OPS_FEATURES_TECH_STEAL_LIST.md` | 14 patterns + file-level pointers | Implementation reference |
| `MASTER_INTEGRATION_PLAN.md` ← *this* | Single executable roadmap with schemas, gates, anti-list | Day-to-day execution |

**This doc supersedes the ship-order sections of the other three.** They remain useful as context/reference but execution follows this plan.
