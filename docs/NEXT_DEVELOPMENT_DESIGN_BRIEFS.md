# HireStack AI Next Development Design Briefs

Date: 2026-04-11

> **STATUS — 2026-04-29 (post v1.0.1, refreshed S13-F4).** This doc is
> superseded by what shipped during S1–S13. Read
> [`audits/S13-roadmap-reconciliation.md`](audits/S13-roadmap-reconciliation.md)
> first. Summary:
>
> - **Brief 1 (Final-State Intelligence Loop) — SHIPPED.**
>   `optimizer_final_analysis` + `fact_checker_final` are in
>   `_STAGE_ORDER`; `final_analysis_report` lives on
>   `PipelineResult`; observability + validator + 3 dedicated tests
>   are wired.
> - **Brief 2 (Replay & Failure Intelligence) — SHIPPED.**
>   `ai_engine/evals/{replay_runner,failure_taxonomy,replay_report}.py`
>   plus admin `replay-drawer.tsx` and 2 test modules. The 10-class
>   taxonomy set is pinned by name in
>   `test_replay_system.py::test_named_class_set_is_pinned` (S13-F4).
> - **Brief 3 (Evidence Graph v1) — SHIPPED.** Migration
>   `20260411000000_evidence_graph_v1.sql` defines the canonical
>   tables with RLS; `ai_engine/agents/evidence_graph.py` feeds
>   the planner. `pipeline_runtime` now invokes
>   `graph_builder.detect_contradictions()` after canonicalize so
>   `evidence_contradictions` actually receives rows in production
>   and the contradiction penalty in
>   `compute_evidence_strength_score()` flows into the planner's
>   risk_mode. Wiring pinned by
>   `test_pipeline_evidence_graph_wiring.py` (S13-F4).
> - **Brief 4 (Adaptive Planner & Strategy Memory) — SHIPPED in
>   S13-F1.** Risk-mode taxonomy `conservative/normal/aggressive` is
>   ratified by [`adrs/0015-planner-risk-mode-and-strategy-memory.md`](adrs/0015-planner-risk-mode-and-strategy-memory.md);
>   strategy-memory primitives ship as separate per-primitive
>   modules under `ai_engine/agents/` (`style_outcome_scorer`,
>   `style_signal_deriver`, `user_style_hints`).
> - **Brief 5 (Mission Control UX v2) — SHIPPED.** Timeline rail,
>   evidence inspector, risk panel, action queue 2.0 all present.
>   Variant Lab shipped in S13-F2 with composite scoring
>   (Evidence 45 / ATS 35 / Readability 20) ratified by
>   [`adrs/0016-variant-lab-winner-pick.md`](adrs/0016-variant-lab-winner-pick.md);
>   AI cannot override the score pick.
>
> All five briefs are now SHIPPED. The remaining surface lives in
> the next-cycle backlog (no S13 residuals open).

## Current Baseline

The platform is now in a materially better state than the original agent pipeline.

- Lifecycle hardening is in place.
- Stage contracts, tool normalization, evidence flow, and observability are wired.
- Final validation now consumes refreshed fact-check and citation state after revisions.
- Backend validation is green on the non-integration suite.

That changes the next priority. The platform does not need more random agent surface area right now. It needs the next layer of system advantage.

The best next sequence is:

1. Final-state intelligence loop
2. Replay and failure intelligence
3. Evidence graph v1
4. Adaptive planner and strategy memory
5. Mission control UX v2

This order is deliberate.

- Step 1 closes the last important quality blind spot in the current pipeline.
- Step 2 gives the team a disciplined way to learn from production failures.
- Step 3 turns evidence from a job-level feature into a platform truth layer.
- Step 4 makes orchestration adaptive instead of static.
- Step 5 exposes the system advantage in the product surface.

## Brief 1: Final-State Intelligence Loop

### Goal

Make the final delivered draft measurable and explainable after all revisions, without reintroducing stale citation risk.

### Why now

The current pipeline refreshes fact-check and citations after revision, but optimizer output is still effectively first-pass only. That means the final delivered document can be safer than before while still under-instrumented from an ATS and readability perspective.

### Design decision

The first version should be analysis-only, not rewrite-capable.

Do not add a final optimizer rewrite stage yet. If the optimizer mutates content after final fact-check, the system reopens the exact truth drift problem that was just fixed.

Instead, add a final analysis stage that scores the delivered draft and produces residual recommendations.

### Proposed stage sequence

researcher -> drafter -> critic/optimizer/fact_checker -> revision loop -> fact_checker_final -> optimizer_final_analysis -> validator

### Output contract

Add a final optimization report that includes:

- final ATS score
- final readability score
- remaining missing keywords
- keyword coverage delta versus first-pass optimizer
- readability delta versus first-pass optimizer
- residual recommendations that were not auto-applied

### Backend changes

Primary file targets:

- ai_engine/agents/orchestrator.py
- ai_engine/agents/optimizer.py
- ai_engine/agents/contracts.py
- ai_engine/agents/observability.py
- backend/tests/unit/test_agents/test_orchestrator.py
- backend/tests/unit/test_contracts.py
- backend/tests/unit/test_observability.py

### Observability additions

Emit:

- initial_ats_score
- final_ats_score
- keyword_gap_delta
- readability_delta
- optimizer_residual_issue_count

### Acceptance criteria

- Final validator context includes final optimization analysis.
- No content mutation happens after final fact-check in v1.
- Pipeline summary exposes initial versus final quality and ATS deltas.
- Regression tests prove final analysis is based on the final revised draft, not the initial draft.

## Brief 2: Replay And Failure Intelligence

### Goal

Turn every failed or low-quality pipeline run into a reusable diagnostic artifact and a regression candidate.

### Why now

The runtime is now durable enough that replay becomes valuable. Without replay, production incidents remain anecdotes. With replay, they become a training loop.

### Product outcome

When a job fails or produces a low-confidence result, the team can reconstruct what happened, classify the failure, and promote it into a permanent regression case.

### First version scope

Build a deterministic replay tool before any rich UI.

The first version should:

- reconstruct the job timeline from generation job events
- load evidence ledger and claim citations
- identify the last safe stage boundary
- rerun deterministic tools against the stored artifacts
- classify the failure into a taxonomy
- emit a replay report suitable for engineering review

### Failure taxonomy v1

Use a fixed taxonomy:

- contract drift
- artifact gap
- evidence binding miss
- citation freshness miss
- stage timeout
- provider failure
- planner misclassification
- low-evidence input
- validator escape

### System design

Add a replay runner module and keep it separate from live pipeline execution.

Suggested targets:

- ai_engine/evals/replay_runner.py
- ai_engine/evals/failure_taxonomy.py
- ai_engine/evals/replay_report.py
- backend/app/api/routes/generate.py for optional admin surface later

### Output shape

Replay report should include:

- job id
- pipeline name
- completed stages
- stage artifacts present or missing
- evidence summary
- citation summary
- detected failure class
- likely root cause
- suggested regression target

### Acceptance criteria

- A failed job can be replayed offline from persisted state.
- Replay produces a stable failure classification.
- At least the top ten failure classes can be expressed in the taxonomy.
- A replay report can be attached to a new regression test or gold case.

## Brief 3: Evidence Graph v1

### Goal

Evolve evidence from job-scoped ledger items into a reusable user truth layer that can power documents, interview prep, salary coaching, and recruiter workflows.

### Why now

The current ledger is good for individual job safety. It is not yet a platform graph. Without a user-scoped truth layer, each job still rediscovers facts locally.

### Core design decision

Keep the current job-scoped evidence ledger intact.

Add a second layer of canonical user evidence rather than replacing the existing model. The current ledger is correct for audit and replay. The new graph is for reuse and contradiction analysis.

### Data model v1

Add canonical entities such as:

- user_evidence_nodes
- user_evidence_aliases
- user_claim_edges
- evidence_contradictions

Recommended semantics:

- user_evidence_nodes stores canonical facts for a user
- evidence_ledger_items remains the job-scoped evidence snapshot
- ledger items link upward to canonical nodes where possible
- claim citations link downward to job evidence and upward to canonical facts when resolved

### Contradiction engine v1

Detect contradictions across:

- company names
- titles
- date ranges
- degree and certification claims
- numeric impact claims when unsupported by any source

### File targets

- ai_engine/agents/evidence.py
- ai_engine/agents/orchestrator.py
- backend/app/core/database.py
- supabase/migrations/*
- frontend workspace evidence views later

### Acceptance criteria

- Canonical evidence identities are distinct from job-scoped evidence ids.
- Job replay remains fully supported.
- Contradiction flags can be generated without mutating source evidence.
- Fact-check and validator can consume contradiction signals.

## Brief 4: Adaptive Planner And Strategy Memory

### Goal

Replace static pipeline policy defaults with a planning layer that selects depth, stages, and budgets based on actual input quality and historical learning.

### Why now

The current policy system is useful but static. Static rules cap the ceiling. A category-leading system should decide when to go deep, when to stay light, and when to escalate confidence or risk.

### Planner output

Introduce a planning artifact before stage execution begins.

The plan should contain:

- jd_quality_score
- profile_quality_score
- evidence_strength_score
- risk_mode
- enabled_stages
- max_iterations
- research_depth
- token_budget_class
- explanation

### Risk modes

Start with four:

- fast
- balanced
- strict
- evidence_first

### Strategy memory

Do not store raw prompt fragments as memory.

Store stable primitives such as:

- preferred tone
- preferred structure density
- strong role-family emphasis patterns
- company-family messaging patterns
- outcomes of accepted versus rejected variants

### File targets

- ai_engine/agents/orchestrator.py
- ai_engine/agents/pipelines.py
- ai_engine/agents/memory.py
- ai_engine/agents/contracts.py
- backend tests for planner decisions

### Acceptance criteria

- Planner produces a persisted plan artifact.
- Stage enablement is explainable from the plan.
- Memory influences strategy but cannot override factual evidence.
- Low-quality inputs can trigger evidence-first or strict planning automatically.

## Brief 5: Mission Control UX v2

### Goal

Expose the system advantage in the workspace so the product feels like a career operating system rather than a black-box generator.

### Constraint

This should extend the existing workspace spec, not replace it.

The current UX direction in the workspace spec is already strong:

- sticky scoreboard header
- sticky coach panel
- task queue
- evidence vault
- two-pane editor patterns

The next design layer should enrich those surfaces with runtime truth and decision visibility.

### Proposed additions

#### 1. Agent Timeline Rail

Add a live or replayable execution timeline showing:

- stage order
- stage duration
- retries
- revision loops
- contract drift markers
- final validation result

#### 2. Evidence Inspector

From the workspace, a user should be able to inspect:

- key claims in the current document
- linked evidence items
- unsupported or embellished claims
- contradiction warnings

#### 3. Risk Panel In Scoreboard Header

Extend the scoreboard with:

- evidence strength
- contradiction count
- unsupported claim count
- residual ATS gaps
- confidence status

#### 4. Variant Lab

Expose side-by-side variant comparison using:

- quality score deltas
- ATS deltas
- evidence coverage deltas
- recommendation on winner and why

#### 5. Action Queue 2.0

Upgrade the coach panel and task queue so they generate actions like:

- collect missing proof
- resolve contradiction
- improve missing keyword coverage
- strengthen weak section
- practice interview stories from verified evidence

### Frontend targets

- frontend/src/app/(dashboard)/applications/[id]/page.tsx
- frontend/src/components/workspace/scoreboard-header.tsx
- frontend/src/components/workspace/coach-panel.tsx
- frontend/src/components/workspace/status-stepper.tsx
- new evidence and timeline components under frontend/src/components/workspace/

### Acceptance criteria

- Users can see why a document is trustworthy or risky.
- The workspace exposes agent decisions, not just final output.
- Evidence and action systems are connected.
- Variant comparison is tied to measurable deltas, not vague preference.

## Recommended Execution Order For Opus

### Wave 1

- Brief 1: Final-state intelligence loop
- Brief 2: Replay and failure intelligence

These are the highest-leverage near-term builds because they improve the current core without reopening truth risk.

### Wave 2

- Brief 3: Evidence graph v1
- Brief 4: Adaptive planner and strategy memory

These turn the improved pipeline into a true system advantage.

### Wave 3

- Brief 5: Mission control UX v2

This should ship on top of the new runtime, replay, evidence, and planner surfaces so the frontend reflects real system capability rather than placeholders.

## What Not To Do Next

Avoid these mistakes in the next phase:

- do not add more rewriting stages after final fact-check unless you also add another truth enforcement boundary
- do not collapse job-scoped evidence and user-scoped canonical evidence into one identifier model
- do not ship adaptive planning without persisted explanations and tests
- do not build flashy agent timeline UI before the replay and telemetry surfaces are stable

## Bottom Line

The next phase should move HireStack from reliable pipeline execution to self-improving system execution.

That means the next development wave is not about adding more generated document types. It is about building:

- a final-state measurement loop
- a replay discipline
- a real truth graph
- an adaptive planner
- a workspace that makes all of that visible

That is the shortest credible path to being materially ahead.
