---
title: Business Logic Context
last_synced: 2026-05-08
watch_paths:
  - backend/app/services
  - ai_engine/agents
  - ai_engine/chains
  - frontend/src/app/(dashboard)
canonical_sources:
  - README.md
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md
update_when:
  - the 7-phase pipeline phases change (rename, add, remove)
  - a new product surface ships (e.g. AIM v2, salary coach v2)
  - a new tier in document_library / evidence ledger is introduced
  - the 3-tier document model changes
---

# Business Logic Context

> What HireStack AI **does for the user.** This file is the bridge between
> code and product. Engineering decisions in the rest of `/context` only
> make sense when you understand which user job they serve.

---

## TL;DR — 12 lines

1. **Single mission:** turn one resume + one job description into a
   personalized, evidence-grounded application package — at LinkedIn-Easy-
   Apply speed but with the depth of a senior recruiter.
2. **Output is not just a CV.** A "generation" produces: tailored CV, cover
   letter, personal statement, ATS scan, gap analysis with study plan,
   evidence ledger, and (optionally) portfolio assets and a slide deck.
3. **The pipeline has 7 phases:** Recon → Atlas → Cipher → Quill → Forge →
   Sentinel → Nova. See [AI_CONTEXT.md](AI_CONTEXT.md) for which agents
   run which phase.
4. **Documents are 3-tiered:** **benchmark** (gold-standard target) →
   **fixed** (the user's evergreen master) → **tailored** (per-application
   variant). All three live in `document_library`.
5. **Evidence is 4-tiered:** VERBATIM > DERIVED > INFERRED > USER_STATED.
   Sentinel rejects DERIVED claims that do not trace to a VERBATIM source.
6. **Multi-tenant from day one.** Free / Pro (individual), Team (small
   recruiter), Enterprise (agency / consultancy with Kanban candidate
   pipeline + RBAC).
7. **AIM** (Application Intelligence Module): RAG-backed insights about a
   target company — recent news, leadership, culture signals, JD analysis.
8. **Missions + cadence**: lightweight goal-tracking (apply N times this
   week, prep for X interview by Friday). Daily learning streaks.
9. **Job sync**: pulls from external job boards (`tracked_companies` +
   `job_sync_runs`) so the user does not need to paste JDs.
10. **Interview simulator**: long-lived agentic session
    (`LongLivedSessionWorkflow`) with role-play turns, signal scoring,
    and post-session debrief.
11. **Salary coach**: per-role / per-region salary analysis with negotiation
    script generation.
12. **A/B Variant Lab**: generate N variants of the same application and
    let the user pick; rank by ATS score + critic notes.

---

## Audiences and tier mapping

| Tier | Who | Cell |
|---|---|---|
| Free | exploring; ≤3 generations / month | shared cell |
| Pro | individual job seeker; per-month subscription | shared cell |
| Team | small recruiter / coach (≤5 seats) | shared cell |
| Enterprise | agency / consultancy with Kanban + RBAC | dedicated cell (paid SKU) |
| API | partner integration (Stage B) | shared cell + API keys |

Tier gates feature flags + quota knobs. The product surface is the same
across tiers; advanced features (A/B Lab, batch, custom benchmarks)
require Pro or higher.

---

## The user journey (canonical)

```
1. Sign up (Supabase auth) -> onboarding wizard creates org + first profile.
2. Upload resume (DOCX/PDF) -> parsed by Atlas profile parser ->
   stored in `profiles` + `profiles_embeddings`.
3. Either:
   a. Paste a JD into "New application", OR
   b. Add a tracked company; job_sync pulls JDs daily; user clicks "Start".
4. Pipeline runs (Recon -> Nova). Mission Control UI streams progress.
5. User receives the application bundle:
     - tailored CV
     - cover letter
     - personal statement
     - ATS scan + recommendations
     - gap analysis with study plan
     - evidence ledger (every claim traces to a source)
     - optional: portfolio asset, slide deck
6. User edits in TipTap, exports to PDF/DOCX, applies.
7. Post-apply: tracks in `applications` table; can launch interview
   simulator and salary coach for the same role.
8. Daily learning streak nudges user to fill gaps identified by Cipher.
```

---

## The 7 phases (what each does for the user)

| Phase | User-visible "thing" | Engineering note |
|---|---|---|
| **Recon** | "We learned about the role and the company." | RoleProfilerChain + CompanyIntelChain + DiscoveryChain |
| **Atlas** | "We built a target benchmark." | BenchmarkChain (gold-standard CV / cover for this role) |
| **Cipher** | "Here are your gaps and the evidence we have." | GapAnalyzerChain + EvidenceLedgerChain |
| **Quill** | "We drafted your CV, cover, and statement." | DocGeneratorChain (parallel) |
| **Forge** | "Here are extras (portfolio piece, deck)." | Portfolio/PPT/LinkedIn agents (optional, gated by feature) |
| **Sentinel** | "We checked the facts and ATS-scanned it." | Critic + FactChecker + ATSScanner |
| **Nova** | "Here is your final bundle." | AssemblyChain — persists to document_library |

A user can re-run Forge or Sentinel on an existing generation without
re-running Quill (variant cost saving). The orchestrator allows phase
restart given a saved checkpoint.

---

## Document library (3 tiers)

```
benchmark  — gold-standard target (what an ideal candidate's CV looks like for this role)
   |
   v
fixed      — the user's evergreen master CV (kept current; not per-application)
   |
   v
tailored   — per-application variant (one per application)
```

Tables:

- `document_library` (3-tier rows)
- `document_catalog` (search index over fixed + tailored documents)
- `application_versions` (tailored docs are versioned per application)

Editing the **fixed** doc updates the master; future generations start
from the new master. Editing a **tailored** doc only affects that
application.

---

## Evidence ledger (4 tiers)

Every claim in a generated document is classified:

| Tier | Definition | Example |
|---|---|---|
| **VERBATIM** | quoted directly from source (resume, JD, public record) | "Led migration of 1.2M users to AWS." (from resume) |
| **DERIVED** | logical inference from a VERBATIM source | "Has experience leading large-scale migrations." (derived from above) |
| **INFERRED** | reasonable assumption from context but not stated | "Comfortable with stakeholder management." |
| **USER_STATED** | user told us in chat / wizard | "I prefer remote-first companies." |

`ff_strict_critic_gate=true` makes Sentinel **reject** DERIVED claims
that do not trace to a VERBATIM source via the evidence graph
(`ai_engine/agents/evidence_graph.py`).

The evidence ledger is visible to the user in the dashboard
(`/dashboard/evidence`) so they can see exactly which words came from
where.

---

## AIM — Application Intelligence Module

`ai_engine/agents/aim/` + `backend/app/api/routes/aim.py`.

For a target company, AIM ingests:

- public website + about pages
- recent news (last 90 days)
- leadership snapshot
- press releases / earnings if public
- the JD itself

Ingestion produces `aim_source` rows + `aim_source_embeddings` for RAG.

User-facing surface (`/dashboard/aim` or per-application AIM panel):

- "Recent signals" timeline
- "Culture indicators" (from job description language + reviews)
- "Talking points" (per the user's profile)
- "Open questions" (what to ask in the interview)

---

## Missions + cadence + learning

- **Missions** (`/dashboard/mission`): "Apply to 5 SRE roles this week."
  Tracked tasks; progress bar.
- **Cadence**: daily streak counter (`learning_streaks`); 5-minute prompt
  per day to address one gap from Cipher.
- **Tracked companies** (`tracked_companies`): watchlist; auto-prep when
  a tracked company posts a matching role.

---

## A/B Variant Lab

`/dashboard/ab-lab`. User runs N variants of one application; each variant
has a slightly different angle (e.g. "leadership-forward" vs "IC-deep").
Variants ranked by:

- ATS score
- Critic factual score
- ATS keyword match
- length / readability

User picks one to apply with; the others are kept for reference.

Implementation: `ai_engine/agents/multi_pipeline.py` fans out N copies of
Quill→Sentinel; Nova picks the highest-ranked unless user overrides.

---

## Batch generation

`/dashboard/batch`. User pastes a CSV of JDs; backend kicks off N
generations in parallel via `BatchGenerationWorkflow` (Temporal). Per-org
concurrency cap (Pro: 3, Team: 10, Enterprise: 50).

---

## Interview simulator

`/dashboard/interview`. Powered by `LongLivedSessionWorkflow` (Temporal
actor) so a session can survive disconnects.

Flow:

1. User picks a role + difficulty.
2. Backend opens a session; an interviewer agent
   (`ai_engine/agents/interview_sim/`) asks turn 1.
3. User answers (text or voice transcript).
4. Signal-scoring agent rates the answer (clarity, depth, evidence, fit).
5. Loop until N turns or user ends.
6. Post-session debrief: per-turn signals + "what to improve" plan.

Sessions persist in `interview_sessions`; transcripts in
`interview_session_turns`.

---

## Salary coach

`/dashboard/salary`. Inputs: role, region, years of experience, current
comp.

Pipeline:

1. SalaryDataAgent pulls market data (per-region buckets).
2. PositioningAgent ranks the user's case (skills, achievements).
3. NegotiationAgent generates a per-step negotiation script.

Output: salary band, expected offer range, negotiation script.

---

## Tracked companies + job sync

- `tracked_companies` table per org.
- `JobSyncWorkflow` (Temporal cron) pulls from configured boards
  (Greenhouse, Lever, etc. — implemented per source).
- `job_sync_runs` records run history + counts.
- New matching JD triggers an `aim.assignment.created` event so the user
  sees a notification "New role matches your watchlist."

---

## Enterprise: agency Kanban

`/dashboard/candidates`. Multi-tenant agency surface:

- `candidates` table (per org).
- Stages: New → Sourced → Interviewing → Offer → Placed → Lost.
- Per-stage kanban; drag to move.
- Each candidate has a profile (parsed resume) and a list of generated
  applications.
- RBAC: owner / admin / member / viewer; viewer is read-only.

Powered by the same `applications` and `profiles` tables, with
`candidate_id` foreign keys.

---

## Knowledge surface

`/dashboard/knowledge`. RAG over the user's own uploaded documents
(resumes, portfolios, project write-ups). Used by:

- Cipher to find evidence for DERIVED claims.
- AIM to enrich company intel with user's prior research.

---

## Export

`/dashboard/export`. Per-application or batch export to:

- PDF (via html2pdf in the browser)
- DOCX (via mammoth round-trip)
- Markdown
- ZIP bundle (CV + cover + statement + evidence + ATS report)

Server-side rendering used for PDF when user has a slow client (Stage B).

---

## How a feature ships (canonical example)

When a new product surface ships (e.g. "Salary coach v2"):

1. Schema: new tables / columns under `supabase/migrations/`.
2. Backend service: `backend/app/services/salary.py` (or new domain folder).
3. Routes: `backend/app/api/routes/salary.py`.
4. AI pieces: chains under `ai_engine/chains/salary_*.py`; agents under
   `ai_engine/agents/salary/`.
5. Frontend: page under `frontend/src/app/(dashboard)/salary/`.
6. Events: any state change emits via `OutboxWriter`; new event type
   gets a JSON schema under `packages/events/schema/v1/`.
7. Tests: backend pytest + frontend vitest + Playwright for the user
   flow.
8. Eval gold set if any chain is non-trivial.
9. Update [AI_CONTEXT.md](AI_CONTEXT.md), [API_CONTEXT.md](API_CONTEXT.md),
   [DATABASE_CONTEXT.md](DATABASE_CONTEXT.md), and this file.
10. Release note in [CHANGELOG.md](../CHANGELOG.md).

---

## What "explicitly NOT in scope"

From the project README and blueprint §17:

- ATS submission automation (we generate; user submits).
- Agentic email/calendar takeover.
- Generic chat assistant (we are job-search-shaped).
- Free-form web crawling outside `safe_fetch` allowlist.
- AI that "applies on the user's behalf" autonomously.
- Storing third-party platform credentials.

---

## What "good business logic" looks like in this repo

- [ ] User-visible job is named explicitly in the PR description.
- [ ] Surface is tier-gated correctly (Free / Pro / Team / Enterprise).
- [ ] All claims trace to evidence (no inventing).
- [ ] Output respects the user's voice (no over-stylizing).
- [ ] Cost is bounded (projection × 1.10; usage_guard cap honored).
- [ ] Failure modes degrade gracefully (no infinite spinners).
- [ ] Multi-tenant from day one (RLS + scope checks).
- [ ] Telemetry: per-feature usage counters + funnel events.
