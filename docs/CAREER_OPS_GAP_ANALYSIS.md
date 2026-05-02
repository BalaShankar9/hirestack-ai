# Career-Ops → HireStack AI: Strategic Gap Analysis

> Source: <https://github.com/santifer/career-ops> (cloned to `reference/career-ops`).
> A single-user CLI tool by Santiago Fernández — used personally to evaluate 740+ jobs
> and land a Head of Applied AI role. MIT-licensed.
> Date: 2026-05-02. Audit performed after ATLAS rebuild + frontend display
> follow-up shipped (commits `5bac50f` → `9018487`).

## TL;DR

Career-ops is a personal Claude Code workflow, not a SaaS — but its **design
patterns** are sharp. After surveying our codebase, ~70% of its capabilities
already exist somewhere in HireStack as backend services
(`career_analytics`, `scan_history_service`, `salary_negotiate`,
`career_monitor`, `interview_sessions`, ATLAS sub-agents, etc.). The real gap
is **experience polish, daily-engagement loops, and a few sharper product
ideas**.

This doc is a prioritized roadmap of what's worth porting, with size estimates
and the specific engineering moves that get us there.

---

## 1. Side-by-side capability matrix

| Career-ops capability | HireStack today | Gap | Recommendation |
|---|---|---|---|
| `oferta` — A-G evaluation per JD | RoleProfilerChain + ATLAS validation + benchmark + scorecard | ✅ richer | Keep — we exceed |
| `oferta` Block G — **Posting Legitimacy** (ghost-job detection) | `scan_history_service` (repost detection) + `/ghost-check` + `PostingLegitimacyChain` | ⚠️ Backend exists, **not exposed in IntelligencePanel** | **TIER 1 (UI)** |
| `oferta` Block F — STAR+R interview prep | `interview_sessions` table + `/interview/*` routes + `interview_prep_guide` doc type | ✅ richer | Keep — we exceed |
| `pdf` — ATS-optimized CV (Space Grotesk + DM Sans) | CV generation w/ multiple style variants | ✅ richer | Keep |
| `scan` — Zero-token ATS API poller (Greenhouse / Ashby / Lever / BambooHR / Teamtailor / Workday) | URL canonicalizer recognizes those hosts; `job_sync` exists; **no scheduled scanner** | 🚨 **Major missing capability** | **TIER 2 (Discovery feed)** |
| `auto-pipeline` — Paste URL → full eval | We do this through the SSE stream | ✅ | Keep |
| `batch` — Mass parallel evaluation | Generation-jobs queue exists | ⚠️ Built but no batch UX | **TIER 3** |
| `followup` — Cadence engine (7/3/1d), urgency dashboard, draft drafts | `follow_up_email` doc type + `career_monitor` interview reminder; **no cadence dashboard** | 🚨 **No daily-action surface** | **TIER 1 (Cadence)** |
| `patterns` — Personal funnel analytics (which archetypes/blockers convert) | `career_analytics.get_conversion_funnel` exists; **no recommendations engine, no UI** | ⚠️ Backend partial, no surface | **TIER 1 (Insights)** |
| `interview-prep` — Per-company Glassdoor/Blind/Leetcode research + Story Bank accumulator | Per-app interview prep; **no cross-application Story Bank** | ⚠️ Stories don't compound | **TIER 2 (Story Bank)** |
| `apply` — Live form-fill assistant (Playwright watches Chrome tab) | Static `follow_up_email` / cover letter docs | 🚨 No live-fill experience | **TIER 3 (Browser ext.)** |
| `deep` — Structured 6-axis company research prompt | Company intel exists in pipeline | ✅ comparable | Keep |
| `training` — "Should I take this course?" 6-dim evaluator | Not present | ❌ | **TIER 3 (niche)** |
| `negotiation` scripts (geo-discount pushback, competing-offer leverage) | `salary_negotiate` route + `salary_negotiation_script` doc | ⚠️ Generic, no leverage frameworks | **TIER 2 (sharper prompts)** |
| 6-archetype role taxonomy (FDE / SA / PM / LLMOps / Agentic / Transformation) used to *tune* every prompt | ATLAS dynamic archetypes are *generated* per JD | ⚠️ No stable taxonomy → harder to compare across JDs | **TIER 2 (taxonomy layer)** |
| Canonical status state-machine (`states.yml` — evaluated / applied / responded / interview / offer / rejected / discarded / skip) | `applications.status` checks `(draft, active, submitted, interview, offer, rejected, withdrawn, archived)` | ⚠️ **Different vocabulary** — we miss `responded` / `discarded` / `skip` semantics that drive the cadence engine | **TIER 1 (status model)** |
| Conductor-mode parallel batch processor (`claude --chrome` worker pool) | Generation-jobs worker exists | ✅ pattern matches | Keep |

---

## 2. The Tier-1 quartet (highest leverage, ship next)

These four are small, leverage existing infra, and dramatically increase
daily engagement & user-perceived intelligence.

### T1.A — Posting Legitimacy panel in IntelligencePanel

**Effort:** ~1 day. **Risk:** very low.

We already have `PostingLegitimacyChain` and `scan_history_service`
producing a legitimacy tier (`legitimate` / `repost` / `evergreen` / `ghost`).
**Nothing in the frontend renders it.** Mirror the new `CandidateValidationPanel`
pattern: a `PostingLegitimacyPanel` mounted under `IntelligencePanel`, fed
from `result.meta.posting_legitimacy` (need to add the SSE plumbing — single
key in `_format_response`).

Output:
- Tier badge (legitimate / repost-N / evergreen-Yd / ghost) with color.
- One-line reasoning ("Reposted 3× since 2025-11; identical JD body").
- "Skip" CTA that auto-sets application status when ghost.

This is **the most differentiated single product moment** career-ops offers
and we already paid for the brain — we just haven't built the face.

### T1.B — Follow-up Cadence dashboard

**Effort:** ~2 days. **Risk:** low.

Career-ops's `followup-cadence.mjs` is 290 lines that compute a single
table: "what should you follow up on today?" Cadence rules:

| Status | First f/u | Subsequent | Max f/ups |
|---|---|---|---|
| applied | 7d | 7d | 2 |
| responded | 1d | 3d | unlimited |
| interview (post-thankyou) | 1d | 3d | unlimited |

Our `career_monitor` only fires interview-prep reminders. Add:
- Migration: `application_followups` table (application_id, channel, sent_at, draft_text, replied).
- Service: `followup_cadence.compute_dashboard(user_id) → list[CadenceItem]` mirroring career-ops's classifier. Use existing `applications.status` + `applications.updated_at` as the spine.
- Route: `GET /api/cadence/today` returns urgent / overdue / waiting / cold buckets.
- UI: new "Today" panel in dashboard sidebar — `<CadenceToday />`. Click → opens app, "Generate draft" calls existing follow-up-email doc generator.

This becomes the **one screen the user opens every morning**. Daily active
loop = retention.

### T1.C — Personal Pattern Insights

**Effort:** ~3 days. **Risk:** low.

Career-ops's `analyze-patterns.mjs` answers: *what's actually working for me?*
Reads all reports + status outcomes, computes:
- Score-threshold recommendation (score ≥ X → 80% positive outcome).
- Archetype conversion rates (which role-shapes I land vs reject).
- Repeated hard blockers (geo / stack / seniority / onsite).
- Tech-stack gap clusters in negative outcomes.
- Top-5 actionable recommendations with reasoning.

We have `career_analytics.get_conversion_funnel` already. Extend it:
- New service `pattern_insights.py` consuming `applications`, `evaluations`, `evidence_graph`.
- Min threshold guard (≥5 outcomes; otherwise show "keep applying" empty-state).
- New route `GET /api/insights/patterns` returning the structured JSON.
- New page `/dashboard/insights` rendering: funnel chart + score-vs-outcome scatter + archetype conversion bars + blocker frequency + recommendations list.

Differentiator vs every CV-generator on the market: **we tell users which
applications are worth their time based on their own data.**

### T1.D — Status taxonomy refactor: add `responded`, `discarded`, `skip`

**Effort:** ~1 day. **Risk:** medium (touches a check constraint in production).

Today: `(draft, active, submitted, interview, offer, rejected, withdrawn, archived)`.
Career-ops uses: `(evaluated, applied, responded, interview, offer, rejected, discarded, skip)`.

The semantic gaps that hurt us:
- **`responded`** — recruiter replied but no interview yet. We can't trigger
  the 1d-cadence rule without it; it currently collapses into `submitted`.
- **`discarded`** — user closed the app for non-rejection reasons (changed
  mind, role disappeared, comp too low). Different from `withdrawn`.
- **`skip`** — evaluated but never applied (system flagged ghost / score < 4).
  Powers the `patterns` "self-filtered" classification.

Migration plan:
1. Additive migration: extend the CHECK constraint to allow the new values.
2. Map UI: `submitted → applied` (label only; same DB value or migrate),
   `withdrawn → discarded` alias.
3. Update `applications` Kanban + filters to surface the new lanes.

Without this, T1.B and T1.C lose ~30% of their analytical signal.

---

## 3. Tier 2 — high-impact, larger scope

### T2.A — Auto-discovery Job Feed (Greenhouse / Ashby / Lever poller)

**Effort:** ~1 week.

Career-ops's `scan.mjs` is 400 lines of zero-token HTTP polling against
public ATS APIs. We already have the URL parsers in `url_canonicalizer`
and a `job_alerts` / `job_scan_history` skeleton. What's missing:

1. **`tracked_companies` table** (org_id, company_slug, careers_url,
   provider, last_scanned_at).
2. **Worker**: `scripts/scan_portals.py` — async fan-out to provider APIs
   with concurrency limit (10), 10s timeout, error budget. Schedulable via
   pg_cron, Railway cron, or a simple FastAPI background task.
3. **Dedup** against `scan_history.url_canonical`.
4. **Title filter**: positive/negative/seniority_boost keywords per user
   (already a column on `job_alerts`).
5. **Auto-evaluate** anything matching the user's filter ≥ score 4.0.
6. **UI**: new `/dashboard/discovery` feed — "5 new roles match your filter
   today, 2 scored ≥4.5".

This converts HireStack from *reactive* (user pastes URL) → *proactive*
(we surface opportunities). Killer differentiator. Reduces user effort by
1 order of magnitude.

### T2.B — Cross-application Story Bank

**Effort:** ~3 days.

Career-ops's `story-bank.md` accumulates STAR+Reflection stories across
every interview prep, building a master library of 5–10 reusable stories
that answer 80% of behavioral questions.

Today every interview-prep run starts from cold. Add:
- Migration: `story_bank` table (user_id, title, archetype_tag,
  situation, task, action, result, reflection, evidence_app_ids[],
  reuse_count, last_used_at).
- During `interview_prep_guide` generation: extract candidate stories
  from the answers, dedupe against existing bank entries by semantic
  similarity (use the embeddings table we already have), promote to
  bank if novel.
- UI: new tab in `/nexus` ("Story Bank") with searchable cards, "rehearse"
  flashcard mode, "use in this app" insertion.

Compounds value: every interview the user does makes the next one easier.

### T2.C — Stable 6-archetype role taxonomy

**Effort:** ~2 days.

ATLAS generates *dynamic* archetypes per JD — great for nuance, bad for
cross-JD comparison. Add a stable classifier (LLM single-shot, 6 labels +
hybrid pair) producing a tag on every JD. Now `patterns` can say "you
convert 60% on Agentic but 0% on Enterprise PM" — a compass, not a map.

Career-ops uses: FDE / SA / PM / LLMOps / Agentic / Transformation. We
should pick our own 6–8 labels suited to our user base (not necessarily
AI-only).

### T2.D — Negotiation leverage frameworks (sharper prompts)

**Effort:** ~1 day.

Career-ops `oferta` block C explicitly trains the model on:
- "Sell senior without lying" framing
- "If they downlevel, accept conditionally with 6mo review"
- Geographic-discount pushback ("the market for this role in EU is X")
- Competing-offer leverage ("I have offer at Y, here's how to use it")

Our `salary_negotiate` is generic. Port these as named negotiation
*scenarios* with structured outputs (script + counter-offer table +
walk-away threshold).

---

## 4. Tier 3 — interesting but lower priority

- **T3.A — Live form-fill assistant** (career-ops `apply` mode). Requires
  a browser extension; high build cost, distribution problem, and most
  users don't fill ATS forms in our tab.
- **T3.B — Training/cert evaluator** (career-ops `training` mode). Niche
  but unique — could be a free public tool for SEO ("should I do this
  bootcamp?").
- **T3.C — Mass batch evaluation UX** (paste 50 URLs → parallel reports).
  We have the worker pool; just no UI surface. Useful for power users.
- **T3.D — TUI / CLI front-end** (career-ops dashboard is Bubble Tea Go).
  Not a fit for a SaaS — skip.

---

## 5. What career-ops does that we should NOT copy

- **Markdown-as-database** (`applications.md`, `follow-ups.md`, etc.).
  Local-first single-user thing; we're multi-tenant SQL. Skip.
- **Spanish-default UI strings** in mode prompts. Awkward for an English-
  primary product.
- **Manual `cv.md` curation** — we have a structured `nexus` profile.
- **Per-job 60-line custom prompts** in `modes/*.md`. We have a chain
  framework that's better-engineered.
- **Scoring rubric (A-F + G letter grades)** — our 0-100 scorecard is more
  granular and machine-comparable. Don't downgrade.

---

## 6. Recommended execution order

1. **T1.A — Posting Legitimacy panel** (1d, frontend-only, near-zero risk). ⭐
2. **T1.D — Status taxonomy refactor** (1d, additive migration). Unblocks T1.B + T1.C signal.
3. **T1.B — Follow-up Cadence dashboard** (2d). First daily-active screen.
4. **T1.C — Personal Pattern Insights** (3d). First proprietary-data moat.
5. **T2.A — Auto-discovery Feed** (1w). Killer differentiator.
6. **T2.B — Story Bank** (3d). Retention compounder.
7. **T2.C — Stable archetype taxonomy** (2d). Multiplies T1.C value.
8. **T2.D — Negotiation leverage scenarios** (1d). Polish.

Total: ~3 weeks of focused work to absorb the best of career-ops and
ship features no other CV/ATS tool has.

---

## 7. Acknowledgements

Career-ops is open-source (MIT) and well-engineered. The `_shared.md`
mode-prompt pattern, the `states.yml` canonical-status idea, and the
`followup-cadence.mjs` urgency classifier are particularly worth
studying directly. None of the porting requires copying code — these
are design ideas, not implementations.
