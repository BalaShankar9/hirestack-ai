# HireStack Agent System — World-Class Plan
>
> Generated 2026-04-21 after the PGRST204 production failure exposed the brittle
> deployed hot path. Honest assessment + concrete roadmap. No fluff.

## TL;DR

We have an **A-grade architecture** (durable runtime, evidence ledger, fact
checker, citation pool, eval gate) and a **B+/B deployed system** because the
job runner that real users hit (`jobs.py`) bypasses the v3 AgentPipeline,
bypasses the durable runtime, bypasses the workflow event store, and emits a
much weaker progress feed than the orchestrator produces. The shiny v3 stack is
exercised by `/api/generate/draft` and the eval runner; production users hit
the legacy chains.

This plan describes the gap per agent, the orchestration gaps, and a 4-phase
roadmap that lifts deployed → world-class without a multi-week rewrite.

---

## Per-agent audit

### 1. Recon (Intel Gatherer)

**Files**: `ai_engine/chains/company_intel.py` (227 lines), `ai_engine/chains/market_intelligence.py` (160), `agents/researcher.py` (590).
**Today**: parallel website crawl + GitHub scan + careers/ATS + JD analysis + market research → synthesis. Each sub-task fires an `agent_status` SSE.
**Strengths**: Real parallelism. Tool registry. Source URLs surface in evidence.
**Gaps**:

- No retry-with-different-source when one tool 502s. A failed careers crawl just produces an empty section in the intel report.
- No staleness signal. We re-crawl Google careers on every run even if the JD hasn't changed.
- Sub-task latencies (`agent_status.latency_ms`) are emitted but not aggregated into a Recon dashboard the user sees.
**To world-class**:
- Source-level circuit breakers + automatic substitution (e.g., careers fails → fallback to LinkedIn jobs scrape).
- Per-source result cache keyed by `hash(company + jd_hash + week)` — 24h TTL on company crawls, 7d on GitHub.
- Confidence score per source surfaced in the UI ("Recon: high confidence on 4 / 6 sources").

### 2. Atlas (Resume Analyst)

**Files**: `agents/researcher.py`, `chains/role_profiler.py` (647), `agents/drafter.py` (345).
**Today**: parses resume → builds candidate benchmark → maps skills.
**Strengths**: Full LLM pipeline with critic + validator.
**Gaps**:

- Resume parsing is a single-shot LLM call. PDF/DOCX OCR errors silently degrade output.
- No confidence-per-claim. If the LLM hallucinates a year of experience, nothing catches it.
- Benchmark is generic — doesn't read previous applications by the same user to bias toward proven patterns.
**To world-class**:
- Two-pass parse: structural extractor (regex + heuristics) + LLM enrichment, then cross-validate.
- Per-field confidence (years_experience: 0.92, current_title: 0.4) shown to the user with "Confirm or correct" affordances.
- Pull `applications` table for the same `user_id`, last 30d, and use top-3 outcomes as few-shot exemplars.

### 3. Cipher (Gap Detector)

**Files**: `chains/gap_analyzer.py` (402), `agents/critic.py` (358).
**Today**: compares candidate skills vs ideal benchmark, ranks gaps.
**Strengths**: Output_scorer chain provides quantitative scoring.
**Gaps**:

- Treats every gap as binary "you have it / you don't." No "you have a related skill that transfers."
- No explanation of *why* each gap matters for *this* JD.
- Doesn't surface what to do to close the gap (the learning plan is generated separately, no link).
**To world-class**:
- Skill graph: when a gap is detected, walk the embedding space to find adjacent skills the candidate has, mark as "transferable evidence." Halves false-negative gap rate.
- Per-gap reasoning trace shown inline ("Marked as gap because the JD mentions Kubernetes 4 times in must-haves").
- Direct link from each gap → corresponding learning plan card → external course.

### 4. Quill (Document Architect)

**Files**: `chains/document_generator.py` (800), `chains/universal_doc_generator.py` (370), `agents/drafter.py` (345).
**Today**: generates CV, cover letter, learning plan via direct chain calls.
**Strengths**: Output is HTML, ATS-friendly. Citation injection from evidence ledger when run via orchestrator.
**Gaps**:

- **`jobs.py` calls these chains directly, NOT via the AgentPipeline.** That means: no evidence-grounded citations on the production hot path, no critic loop, no fact-checker, no validator. The user sees the raw drafter output. This is the single biggest deployed-grade hit.
- No A/B between styles (concise vs narrative, achievement-led vs responsibility-led). User can't pick.
- Versions are stored (`cv_versions` JSONB) but not exposed for diff/compare in the UI.
**To world-class**:
- **Migrate `jobs.py` runner onto AgentPipeline + WorkflowRuntime**. This is the multi-day refactor that lifts deployed grade A-. See Phase 2 below.
- Generate 2 variants per artefact (default + alternate), surface both in the workspace, let the user lock the preferred one.
- Side-by-side diff view for any two `cv_versions` entries.

### 5. Forge (Portfolio Builder)

**Files**: `chains/document_generator.py` (portfolio + statement paths).
**Today**: generates personal statement and portfolio HTML.
**Gaps**:

- Portfolio is a generic template. No project-specific tailoring against the actual JD.
- Statement reuses the cover-letter prompt with minor variation — outputs feel templated.
**To world-class**:
- Forge consults a "career-narrative graph" built from the user's evidence ledger items: pull top 3 narratives the user has stated → weave them into the statement.
- Portfolio generates per-project deep-dives only for projects whose tags overlap with the JD top-10 keywords.

### 6. Sentinel (Quality Inspector)

**Files**: `agents/fact_checker.py` (302), `agents/schema_validator.py` (428), `agents/validation_critic.py` (240).
**Today**: validates schema, fact-checks claims against evidence, scores ATS compliance.
**Strengths**: Real fact-checker with evidence linking. Citation coverage metric was added in `9f4b359`.
**Gaps**:

- Sentinel's quality score isn't shown to users with reasoning. It's a number.
- Fact-checker findings (which claims are unsupported) are buried in the response, not surfaced as actionable rewrites.
- No "block publish" gate — if Sentinel rejects, the user still gets the document.
**To world-class**:
- Quality report card in the workspace: per-dimension scores + "what would lift each by 10 points."
- Highlighted rewrite suggestions for any unsupported claim, one-click accept.
- Configurable strictness: "draft mode" allows low scores, "publish mode" requires >80 on all dimensions.

### 7. Nova (Final Assembler)

**Files**: `chains/document_pack_planner.py` (355), assembly logic in `jobs.py`.
**Today**: assembles the final bundle (CV + CL + benchmark + gaps + portfolio).
**Gaps**:

- No bundle-level coherence check (e.g., does the cover letter narrative match the CV summary?).
- Export formats are PDF/DOCX/zip. No "submit-ready" pre-flight (file naming convention, file size, embedded metadata stripping).
**To world-class**:
- Cross-document coherence pass: checks that key claims appear in both CV and CL, flags contradictions.
- Pre-flight checklist: file names, metadata strip, optional pseudonymisation for blind hiring.

---

## Orchestration & integration audit

### What we have

- `WorkflowRuntime` (807 lines) — event-sourced durable execution with timeout, retry, heartbeat, cancel. Tested.
- `AgentPipeline` (1728 lines) — policy-driven stage execution. Used by `/api/generate/draft`.
- `EvidenceLedger` (635 lines) — content-hash IDs, 4 tiers, citation tracking.
- `PipelineMetrics` (227 lines) — emits structured observability summary on every run.
- `generation_job_events` table — sequence-numbered event log per job, replayable as SSE.

### What hurts

1. **The runtime is an island.** `jobs.py` (the production hot path, 2818 lines) does **not** call `AgentPipeline.execute()`. It calls `chains/*` directly. So the durable runtime, evidence ledger, fact-checker, validator, and citation tracking are dark on production traffic.
2. **No replay-from-event for inflight jobs.** On startup, `_finalize_orphaned_job` marks anything `running` → `failed`. A user mid-generation when Railway redeploys loses their work. Should reconstruct from `generation_job_events`.
3. **Cross-job state.** `AgentMemory` exists but is per-pipeline. There's no per-user persistent memory of "Sarah prefers concise CV style" or "her last 3 applications scored highest with achievement-led narrative."
4. **Event taxonomy is shallow.** `generation_job_events` rows are keyed by `event_name = "progress" | "detail" | "agent_status" | "error"`. No `tool_call`, `tool_result`, `cache_hit`, `evidence_added`, `claim_grounded`, `policy_decision`. Means: live agent log is a lot less interesting than it could be.
5. **No global activity surface.** Agent logs are visible only on `/new` (the wizard). The workspace page (`/applications/[id]`) has zero live feed when a regenerate is running. Users staring at "regenerating…" spinner with no transparency.
6. **No automated A/B.** We have a controlled-variants design but it's not wired to user feedback — the system can't learn that style B converts to interview at a higher rate.

---

## 4-Phase Roadmap

### Phase A — "Logs everywhere" (1–2 days, **starting NOW**)

Goal: every page where an agent might be working shows the live feed.

- ✅ DONE in this commit: `LiveAgentActivityDock` component mounted in dashboard layout. Auto-detects user's running jobs via realtime, shows collapsible drawer with per-agent log feed. Visible on every `/dashboard/*` page.
- ✅ DONE: `useActiveGenerationJobsForUser` hook (realtime channel filtered by `user_id` + active statuses).
- TODO: enrich event taxonomy. Add `tool_call`, `tool_result`, `cache_hit`, `evidence_added`, `policy_decision` event names so the dock shows what the agent is *thinking*, not just "Recon: running."
- TODO: backend: `_publish_generation_event` should accept these new event names; emit from `tool_normalizer.py` and `evidence.py` populate hooks.

### Phase B — Migrate `jobs.py` to AgentPipeline (3–5 days)

Goal: lift deployed grade A-. The job runner stops calling chains directly and invokes `AgentPipeline.execute()` per requested module, with the workflow event store wired to `generation_job_events`. This is the single highest-leverage change.
Concrete steps:

1. Add `EventStoreToGenerationJobEventsAdapter` that translates `WorkflowEvent` → row in `generation_job_events`.
2. Pull each module-generation block out of `jobs.py` and into `_generate_module_via_pipeline(module, application, user)` that builds the policy, runs the pipeline, returns a typed result.
3. Implement startup recovery: on boot, scan `generation_jobs` where status=running, reconstruct state from events, resume.
4. Snapshot 425 agent tests pre-change, gate the merge on zero regression.

### Phase C — Per-user memory + style learning (1 week)

Goal: agents remember.

1. New table `user_agent_memory` keyed by `(user_id, memory_type, key)`. Stores: preferred style, target seniority, recurring claim language, do-not-mention phrases.
2. `AgentMemory.load_user_memory(user_id)` injected into all agent prompts.
3. Outcome tracking: when a user marks an application "applied" → "interview" → "offer," update style scores so the planner picks higher-converting variants for future runs.

### Phase D — Multi-variant generation + UI (1 week)

Goal: stop forcing a single output.

1. Quill generates 2 CV variants per run (concise vs narrative) — currently one. Cost ≈ 1.4× because second variant reuses same evidence + research.
2. Workspace shows both, user picks one to lock; loser is archived.
3. Forge does the same for personal statement.
4. Outcome data feeds back into the planner.

---

## Acceptance criteria for "world-class"

The grade lifts to **A on deployed** when all four hold:

| # | Criterion | How we verify |
|---|---|---|
| 1 | Production hot path runs through `AgentPipeline` + `WorkflowRuntime` | grep `jobs.py` for `chain.create_*` direct calls → zero |
| 2 | Mid-deploy job survival | Kill backend mid-run, redeploy, job resumes from event log |
| 3 | Live agent feed visible on every dashboard page | Manual: open `/applications/X`, click regenerate, see dock open with per-agent stream |
| 4 | Citation coverage ≥ 0.6 on production runs (not just eval gate) | `pipeline_observability_summary` log query in Sentry, p50 over 7 days |

---

## Honest gap-to-grade matrix

| Phase | Effort | Gain on deployed grade |
|---|---|---|
| A: Logs everywhere | 1–2 d | B+ → A- on transparency dimension |
| B: Migrate `jobs.py` | 3–5 d | B+ → A on the architectural dimension |
| C: User memory | 1 wk | A → A on personalization dimension |
| D: Multi-variant | 1 wk | A → A+ on output quality dimension |

Phase A ships in this same commit alongside this document.
