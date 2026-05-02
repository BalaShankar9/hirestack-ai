# Career-Ops Features & Tech — Deep Steal-List

> Companion to `CAREER_OPS_GAP_ANALYSIS.md` (parity) and
> `HIRESTACK_VIRALITY_PLAYBOOK.md` (distribution). This doc is **purely
> technical**: which algorithms, data structures, prompts and UX patterns
> are worth porting verbatim, and exactly where they slot into our codebase.
> Date: 2026-05-02.

## Career-ops at a glance (the actual asset list)

```
14 mode prompts (modes/*.md)          → ~3,200 lines of evaluation logic
17 .mjs scripts                       → ~3,800 lines of utilities
 1 Go TUI (dashboard/)                → ~1,000 lines
 1 LaTeX + 1 HTML CV template
 1 portals.yml (45 companies preset)
 1 states.yml (8 canonical statuses)
```

Pure reasoning code is small (~8K LOC). The genius is in **patterns**, not LOC. Below: each pattern, what it does, what we have, and the steal.

---

## 1. The "zero-token portal scanner" pattern (`scan.mjs`, 367 lines)

### What it does
Hits Greenhouse / Ashby / Lever **public job-board APIs** directly — no LLM, no Playwright for listing pages, no browser. Pure HTTP+JSON. Concurrency 10, 10-second timeout. Dedup against URL-set + company×role-set. Filter by positive/negative title keywords.

### The actual API endpoints (these are gold — most people don't know they're public)
```
GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
GET https://api.lever.co/v0/postings/{slug}
```
Each returns ~100 jobs in <500ms with **structured JSON** including title, location, comp band when posted, ATS-stable URL.

### What HireStack has
- `url_canonicalizer.py` recognizes those hosts → ✅
- `job_scan_history` table with `url_canonical` → ✅
- `job_sync.py` skeleton → ⚠️ exists but unused
- **No scheduled fan-out** ❌
- **No tracked_companies table** ❌
- **No title-filter config per user** ❌

### Steal exactly this
1. New table `tracked_companies (user_id, slug, ats_provider, ats_slug, careers_url, enabled, last_scanned_at)`.
2. New service `backend/app/services/portal_scanner.py` with a `_PROVIDER_PARSERS = {"greenhouse": ..., "ashby": ..., "lever": ...}` dict mirroring career-ops's parsers verbatim (they're 5 lines each).
3. Add `workday`, `smartrecruiters`, `bamboohr`, `teamtailor` parsers — career-ops only does Big 3, we one-up by covering the long tail.
4. Worker: cron-driven (Railway scheduled job hits `POST /internal/scan/run`). Fan-out with `asyncio.gather(*[fetch(p) for p in providers], return_exceptions=True)` + `asyncio.Semaphore(10)`.
5. Per-user `title_filter` JSONB column on `job_alerts` (already exists — extend schema to include `positive`, `negative`, `seniority_boost` lists).
6. Auto-evaluate hits scoring ≥ 4.0 → enqueue to `generation_jobs`.

### Why this beats LinkedIn / Teal / Huntr
None of them poll ATS APIs directly. They scrape aggregator sites that are 24h+ stale. We can be 30 minutes fresh **and free** (no LLM cost).

---

## 2. Liveness/expired classifier (`liveness-core.mjs`, 78 lines)

### What it does
Decides "is this job posting still live?" deterministically, **multi-language**:

```js
HARD_EXPIRED_PATTERNS = [
  /job (is )?no longer available/i,
  /position has been filled/i,
  /no longer accepting applications/i,
  /diese stelle (ist )?nicht mehr besetzt/i,   // German
  /offre (expirée|n'est plus disponible)/i,    // French
  ...
]
APPLY_PATTERNS = [/\bapply\b/i, /\bsolicitar\b/i, /\bbewerben\b/i, /\bpostuler\b/i]
MIN_CONTENT_CHARS = 300
```

Algorithm: 404/410 → expired. URL contains `?error=true` → expired. Body matches expired pattern → expired. Apply control visible → **active**. Listing-page pattern → expired. Body < 300 chars → expired (likely just nav/footer). Otherwise → uncertain.

### What HireStack has
`job_watchdog.py` exists but does scheduled hygiene, not on-demand liveness.

### Steal exactly this
1. New module `backend/app/services/liveness_classifier.py` — port the regex tables verbatim, extend with PT/JA/KO/HI/ZH patterns (we beat them on i18n).
2. New endpoint `POST /api/jobs/liveness {url} → {status: expired|active|uncertain, reason, http_status, age_days}`.
3. Wire into the **public ghost-check tool** (Move 1 of virality playbook).
4. Cache results 24h in Redis keyed by canonical URL.

This is the single highest-ROI port: 78 lines → a public utility users can hit anonymously.

---

## 3. The 8-status canonical state machine (`states.yml`)

```yaml
- evaluated   # we ran A-G evaluation, no application yet
- applied     # user submitted
- responded   # recruiter replied (any signal)
- interview   # interview scheduled or in progress
- offer       # offer extended
- rejected    # company rejected
- discarded   # user closed for non-rejection reasons
- skip        # ghost / score < 4 → never apply
```

### Why this matters
The **cadence engine, the funnel analytics, and the pattern recommendations all key off this taxonomy**. With our current statuses, you literally cannot answer "what's my response rate?" because `responded` doesn't exist.

### What HireStack has
`(draft, active, submitted, interview, offer, rejected, withdrawn, archived)` — different vocabulary, missing `responded` and `skip` (the two that drive analytics).

### Steal exactly this
- Additive migration: extend the CHECK constraint to allow the 3 new values.
- Service-layer enum in `backend/app/models/application_status.py` with **alias map** (`submitted → applied`, `withdrawn → discarded`) so old data keeps working.
- UI: keep current labels but add a "Did they reply?" quick-action that flips to `responded` (one-click → unblocks 1d-cadence rule).

**Time:** 1 day. **Without this, items 4, 7, 11 below are crippled.**

---

## 4. Cadence engine (`followup-cadence.mjs`, 339 lines)

### The actual rules (steal verbatim)
| State | First f/u | Subsequent | Max f/ups | Cap-after-no-reply |
|-------|-----------|------------|-----------|---------------------|
| applied | 7d | 7d | 2 | go cold |
| responded | 1d | 3d | unlimited | — |
| interview (post-thank-you) | 1d | 3d | unlimited | — |
| offer | same-day decision window | — | — | — |

Buckets returned daily: `urgent` (overdue >2d), `due_today`, `coming_up` (next 3d), `cold` (max f/ups hit, no reply), `closed`.

### Output shape
```json
{
  "date": "2026-05-02",
  "buckets": {
    "urgent":    [{ "id": "...", "company": "Acme", "role": "AI PM", "days_overdue": 4, "status": "applied", "suggested_channel": "email", "draft_body": "..." }],
    "due_today": [...],
    "coming_up": [...],
    "cold":      [...]
  },
  "recommendations": {
    "stop_following_up": ["..."],
    "consider_withdrawing": ["..."]
  }
}
```

### Steal exactly this
1. Migration: `application_followups (id, application_id, channel ENUM(email,linkedin,phone), sent_at, draft_body, replied_at NULL)`.
2. Service `backend/app/services/cadence.py:compute_dashboard(user_id) → CadencePayload`.
3. Route `GET /api/cadence/today`.
4. UI `<CadenceToday />` mounted as the dashboard's first widget.
5. Each row: "Generate draft" button calls existing `follow_up_email` doc generator → opens prefilled compose window.
6. **Daily 7am email** sending the same payload (Move 6 of virality playbook).

**The single screen the user opens every morning.** This is the DAU loop.

---

## 5. Pattern Insights (`analyze-patterns.mjs`, 550 lines)

### What it computes (each section is a separate render)
1. **Funnel** — applications → responded → interview → offer with conversion rates.
2. **Score-vs-outcome scatter** — *"applications scoring ≥ 4.2 had 81% positive outcome; recommend threshold = 4.2"*.
3. **Archetype breakdown** — conversion rate per archetype (which role-shapes you actually land vs reject).
4. **Blocker analysis** — frequency of `geo`, `stack`, `seniority`, `onsite`, `comp` blockers in your reject pile.
5. **Tech-stack gap clusters** — keywords appearing in negative outcomes vs positive.
6. **Top-5 actionable recommendations** with reasoning, e.g. *"You convert 0% on Enterprise PM despite applying to 7. Consider deprioritizing this archetype."*

### What HireStack has
`career_analytics.get_conversion_funnel` covers item 1. Items 2–6: nothing.

### Steal exactly this
- New service `backend/app/services/pattern_insights.py` consuming `applications`, `evaluations`, `evidence_graph`, `evaluations.scorecard.global_score`.
- Min-threshold guard (≥5 outcomes total; otherwise show empty-state "keep applying — need 5 data points").
- New route `GET /api/insights/patterns`.
- New page `/dashboard/insights` with Recharts: funnel + scatter + bars + frequency + recommendation cards.

**This is our proprietary-data moat.** Every CV generator can write a CV. Only HireStack can tell you *"based on your 47 applications, here's what's actually working."*

---

## 6. Story Bank pattern (`interview-prep/story-bank.md`)

### What it does
Every interview-prep run extracts STAR+R stories from the candidate's answers. Dedupe by semantic similarity to existing bank entries (career-ops uses LLM judge; we have embeddings already). Promote new ones. Result: 5–10 master stories that answer 80% of behavioral questions.

### Why STAR+R (with Reflection) matters
The fifth letter is the unlock. Career-ops's `oferta.md` says it explicitly:
> *"Reflection captures what was learned or would be done differently. Junior candidates describe what happened; senior candidates extract lessons."*

That single column flips the perceived seniority of an answer. Our current interview prep doesn't ask for it.

### Steal exactly this
- Migration: `story_bank (id, user_id, title, archetype_tag, situation, task, action, result, reflection, evidence_app_ids[], reuse_count, last_used_at, embedding vector(1536))`.
- During `interview_prep_guide` generation: extract candidate stories, semantic-dedupe against existing bank using pgvector cosine similarity (threshold 0.85), promote novel ones, increment `reuse_count` on matches.
- New tab in `/nexus`: "Story Bank" — searchable, "rehearse" flashcard mode, "use in this app" → injects into current interview prep doc.
- **Append "& Reflection" column to every existing STAR table our chains output.**

---

## 7. Self-rewriting prompts (`modes/_shared.md` + `modes/_profile.md`)

### The pattern
Career-ops splits prompts into **system layer** (`modes/_shared.md`, auto-updatable) and **user layer** (`modes/_profile.md`, never overwritten). System updates flow in via `update-system.mjs check` without clobbering personalization.

CLAUDE.md tells the agent:
> *"When the user asks to customize anything, ALWAYS write to `modes/_profile.md`. NEVER edit `modes/_shared.md` for user-specific content."*

### Why this is genius
- Users feel agency ("the AI customized itself for me").
- Updates ship without breaking customization.
- The CLI literally **edits its own prompt files** in response to user requests in chat.

### Steal this for HireStack
We can do better as a SaaS: a `user_prompt_overrides` JSONB on the `user_profile` row that gets templated into our chain prompts. Surface a `/settings/voice` page where the user describes **their own framing** ("I'm a founder pivoting to PM — emphasize transferable skills and downplay engineering depth"). LLM-distill into a 200-token system-prompt patch. Apply to every chain that runs for them.

This makes the assistant feel **personal in a way no competitor's does** because we're literally rewriting our prompts per user.

---

## 8. The 6-archetype taxonomy (`modes/_shared.md` archetype table)

### Career-ops's labels (AI-niche)
LLMOps · Agentic · Forward-Deployed Engineer · Solutions Architect · Product Manager · Transformation

### Why a stable taxonomy matters
ATLAS generates *dynamic* archetypes per-JD — great for nuance, **bad for cross-JD comparison**. Without stable labels, "you convert better on X than Y" is impossible to compute.

### Steal this
- Add a stable classifier (single LLM call, 6–8 labels + hybrid pair) producing a `role_archetype` tag on every JD.
- Store on `applications.meta.stable_archetype`.
- Pick 6–8 generalist labels suited to our user base — *not* AI-only. Examples:
  `IC-Engineer`, `Engineering-Lead`, `Product`, `Data/ML`, `Design`, `Sales/CS`, `Operations`, `Founder/GM`.
- Now `pattern_insights.archetype_breakdown` (item 5) actually works.

---

## 9. Negotiation leverage as named scenarios (`modes/_shared.md` Negotiation section)

### What career-ops does
The salary section has *specific named playbooks* with literal scripts:

| Scenario | Script outline |
|---|---|
| Geographic discount pushback | "The market for this role in EU is X; let me explain why region pricing doesn't fit here..." |
| Competing offer leverage | "I have an offer at $Y from Z; here's what I'd need from you..." |
| Downlevel acceptance | Accept conditional on 6-mo review with explicit promotion criteria (text provided). |
| Sell-senior-without-lying | Frame founder/IC hybrid experience as senior IC + scope. |

### What HireStack has
`/api/salary/negotiate` returns generic counter-offer text. Not enough.

### Steal this
- Add a `scenario` enum param to `/api/salary/negotiate`: `geo_pushback | competing_offer | downlevel_accept | sell_senior | first_offer | exploding_offer`.
- Each scenario = a named prompt template with structured output (script + counter-offer table + walk-away threshold + 3 follow-up rebuttals to expected pushback).
- UI: card-deck picker on the salary page — *"What situation are you negotiating?"*

This is **45 minutes of prompt engineering for a 10×-better feature.**

---

## 10. Pipeline integrity scripts pattern

Career-ops has 5 cron-style integrity scripts:

| Script | What it does | HireStack equivalent |
|---|---|---|
| `verify-pipeline.mjs` | Health check: status legality, dup company×role, broken report links | **Missing** — add `POST /internal/integrity/scan` |
| `dedup-tracker.mjs` | Removes duplicate entries | We have URL canonicalization, but not company×role dedup |
| `normalize-statuses.mjs` | Maps aliases → canonical | Needed after status-taxonomy refactor (item 3) |
| `merge-tracker.mjs` | Merges batch worker output | `generation_jobs` worker covers this |
| `cv-sync-check.mjs` | Validates that CV templates resolve all required vars | Useful for nexus profile completeness |

### Steal this
A single `backend/app/services/integrity.py` module with check functions, a `POST /internal/integrity/scan` route (admin-only), and an admin-dashboard widget that surfaces issues. **Not user-facing — operational hygiene.** Catches data drift before it hits users.

---

## 11. Update channel pattern (`update-system.mjs`)

### What it does
On first message of a session, the agent silently runs `node update-system.mjs check` against `https://github.com/.../VERSION` and either says nothing or surfaces:
> *"career-ops update available (v1.5 → v1.6). Your data will NOT be touched. Want me to update?"*

Updates are file-level rsync against the system layer, never the user layer.

### Why this is brilliant for a CLI
Distribution + retention in one channel. Users **see the product evolving in their own terminal**.

### SaaS analog for HireStack
- "What's New" panel in the dashboard powered by a `/api/changelog` feed (we already have release notes — surface them).
- For breaking changes: an inline "Apply migration" CTA that walks user through (e.g., "We added 3 statuses — would you like to map your historical apps?").
- **Trigger after every prod deploy** — turns deploys into a touch-point.

---

## 12. The "ATS-keyword-injected" CV template

### What career-ops does
- Two templates: HTML (Playwright→PDF) and LaTeX (pdflatex).
- Self-hosted fonts (Space Grotesk + DM Sans) — no Google Fonts FOUT, ATS-safe.
- **Color tokens kept in CSS variables** so customization = one variable change.
- Single-column layout (multi-column trips ATS parsers).
- Keywords injected from JD analysis into a hidden screen-reader-only block? **No** — career-ops keeps them visible in the standard sections (Skills, Summary). Stuffing hidden is a known ATS rejection signal.

### What HireStack has
Multiple CV style variants ✅. We're ahead on this.

### Steal these two specifics
1. **Self-host the fonts.** Currently we likely Google-Font-load. Pin Space Grotesk + DM Sans + Inter into our public/. Removes a network dep, fixes a class of PDF-render bugs.
2. **Add a LaTeX/Overleaf export button.** Power users (engineers, academics) want LaTeX. Career-ops's `cv-template.tex` is 200 lines and battle-tested. Generate alongside HTML on every CV gen. Tiny effort, big appeal to a vocal niche.

---

## 13. The Dashboard TUI (Go + Bubble Tea)

### Should we copy?
**No.** Bad ROI for a SaaS — we already have a web UI.

### But steal the IA (information architecture):
- **6 filter tabs**: All · Evaluated · Applied · Interview · Top (≥4) · Skip
- **4 sort modes**: Score · Date · Company · Status
- **Grouped vs flat** toggle (group by status or company)
- **Inline status picker** (no modal — keyboard-friendly)
- **Lazy-loaded report previews** (on hover/focus, not full-page navigation)

Apply this to our Kanban / list views. Currently we're heavier — fewer filters, more clicks, more modals. **Career-ops's TUI is faster than our React app at the core triage task.** That's embarrassing and fixable.

---

## 14. The README itself as a feature

Career-ops's README is the product's homepage. The structure:

1. Hero banner + tweetable thesis
2. 9-language toggle row
3. Demo gif (90 seconds, real terminal session)
4. *"740 jobs · 100 CVs · 1 dream role"* hard-numbers line
5. Feature table (one line each)
6. Quick start (5 commands)
7. Architecture diagram (ASCII)
8. Pre-configured portals list (45 brand names → keyword authority)
9. Tech-stack badges
10. Star History chart
11. Disclaimer (legal trust)
12. Contributors graphic
13. *"Got hired? Share your story"* issue template link

### Steal this **structure** for hirestack.ai homepage
Above-the-fold = thesis + demo gif (autoplay, muted, looping) + numbers. Below = 45-company logo wall ("scanned daily") + ASCII architecture diagram + "Got hired?" wall of stories. **Treat the homepage like an open-source README.** It converts better than any SaaS landing.

---

## Tech-stack absorption decisions

| Their choice | Should we adopt? | Why |
|---|---|---|
| Markdown-as-database (`applications.md`) | ❌ No | Single-user pattern; we're SQL multi-tenant |
| TSV for batch transport | ❌ No | We have generation_jobs queue |
| Playwright for portal scrape | ⚠️ Only for non-API providers | Use ATS APIs first; Playwright only as last resort |
| Self-hosted Space Grotesk + DM Sans | ✅ Yes | Removes Google Fonts dep, ATS-safer |
| Bubble Tea Go TUI | ❌ No | Wrong form factor |
| LaTeX export | ✅ Yes | Niche but high-affinity audience |
| YAML config over JSON | ✅ For user-edited config | We already use this in some places — extend |
| `js-yaml` parser | n/a | We're Python; use PyYAML |
| MIT license | n/a | We're SaaS; can dual-license (open-source the public utilities) |
| Discord community | ✅ Yes | Move 8 of virality playbook |

---

## Recommended port order (tech-only, ignoring marketing)

| # | Item | Effort | Unblocks |
|---|---|---|---|
| 1 | Status taxonomy (item 3) | 1d | items 4, 5, 11 |
| 2 | Liveness classifier (item 2) | 1d | public ghost-check |
| 3 | Cadence engine (item 4) | 2d | morning brief, DAU loop |
| 4 | Stable archetype (item 8) | 1d | item 5 |
| 5 | Pattern insights (item 5) | 3d | proprietary moat |
| 6 | Portal scanner (item 1) | 5d | discovery feed |
| 7 | STAR+R column + Story Bank (item 6) | 3d | interview prep moat |
| 8 | Negotiation scenarios (item 9) | 1d | salary feature polish |
| 9 | Self-rewriting prompts (item 7) | 2d | personalization moat |
| 10 | LaTeX CV export (item 12) | 1d | niche delight |
| 11 | Integrity scripts (item 10) | 2d | operational hygiene |
| 12 | Update channel UX (item 11) | 1d | retention loop |
| 13 | TUI-inspired filter UX (item 13) | 2d | triage speed |

**Total:** ~25 dev-days. Roughly 5 weeks if shipped solo. The first 5 items (8 days) deliver 80% of the value.

---

## What we already do better than career-ops

So we don't accidentally regress:

- **Multi-tenant SQL** with RLS — career-ops is single-user files
- **Streaming SSE pipeline** with per-stage progress — career-ops is blocking
- **ATLAS dynamic sub-agents** with archetypes/candidate-validation/intelligence — career-ops has flat A-F prompts
- **Evidence graph + provenance** — career-ops has no audit trail
- **Multi-org support** with elevation — career-ops has none
- **Web Kanban + benchmark + scorecard donut UI** — career-ops is a CLI
- **Generation-jobs queue** with retry/dedup — career-ops uses bash + claude -p
- **Embeddings/pgvector** — career-ops doesn't have this; we should use it for Story Bank dedup

We are *technically* ahead. We are *experientially and distributively* behind. That's the gap to close.

---

## The TL;DR of the TL;DR

Steal these **five things in order** and we get most of the upside without bloating the codebase:

1. **Status taxonomy refactor** (1d) — unblocks everything else
2. **Liveness classifier as public utility** (1d code + 3d tool surface) — viral SEO + DAU magnet
3. **Cadence engine + morning brief** (2d code + 1d email infra) — DAU loop
4. **Pattern insights with stable archetypes** (4d) — proprietary moat
5. **Portal scanner** (5d) — proactive feed differentiator

That's **15–17 dev-days for full transformation** of the product surface, layered on top of the strong backend we already have.
