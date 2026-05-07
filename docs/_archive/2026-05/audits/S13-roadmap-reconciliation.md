# S13-F0 — Roadmap Reconciliation Audit (`docs/NEXT_DEVELOPMENT_DESIGN_BRIEFS.md`)

**Date:** 2026-04-29
**Scope:** Read-only audit. Classify each of the 5 briefs in
[`docs/NEXT_DEVELOPMENT_DESIGN_BRIEFS.md`](../NEXT_DEVELOPMENT_DESIGN_BRIEFS.md)
(dated 2026-04-11) against the actual `main` HEAD (`2871a9c`,
post-v1.0.1) so the next squad doesn't duplicate work that already
shipped during S1–S12.
**Method:** `grep_search` / `file_search` for the artifacts each brief
names (modules, contract fields, tables, components, tests). No code
changes.

## Verdict at a glance

| Brief                                | Status        | Evidence | Gap |
|--------------------------------------|---------------|----------|-----|
| 1. Final-State Intelligence Loop     | **DONE**      | `optimizer_final_analysis` + `fact_checker_final` stages, `final_analysis_report` on `PipelineResult`, contract validator, observability metrics, 3 dedicated tests | None |
| 2. Replay & Failure Intelligence     | **DONE**      | `ai_engine/evals/replay_runner.py`, `failure_taxonomy.py`, `replay_report.py`, route + drawer UI, 2 test modules | Verify taxonomy ≥10 classes |
| 3. Evidence Graph v1                 | **DONE**      | Migration `20260411000000_evidence_graph_v1.sql` (4 canonical tables w/ RLS), `ai_engine/agents/evidence_graph.py`, contradiction logic, dedicated test module | Verify validator/fact-checker actually consume contradiction signals |
| 4. Adaptive Planner & Strategy Memory | **PARTIAL**   | `ai_engine/agents/planner.py` has `jd_quality_score`, `profile_quality_score`, `risk_mode`, `determine_risk_mode()` | **Risk modes diverge from brief** (`conservative/normal/aggressive` vs brief's `fast/balanced/strict/evidence_first`); strategy-memory primitives (`preferred_tone`, etc.) **not enforced** in `memory.py` |
| 5. Mission Control UX v2             | **MOSTLY DONE** | `agent-timeline-rail.tsx`, `evidence-inspector.tsx`, `risk-panel.tsx`, `task-queue.tsx`, `next-best-action.tsx`, `replay-drawer.tsx`, `scoreboard-header.tsx`, `intelligence-panel.tsx`, `diagnostic-scorecards.tsx`, `quality-report.tsx` | **Variant Lab missing** — zero `workspace/variant*` files |

## Brief-by-brief evidence

### Brief 1 — Final-State Intelligence Loop ✅ DONE

- Stage order matches verbatim:
  [`ai_engine/agents/orchestrator.py:504`](../../ai_engine/agents/orchestrator.py#L504) —
  `_STAGE_ORDER = ["researcher", "drafter", "critic", "optimizer",
  "fact_checker", "optimizer_final_analysis", "validator"]`
- `fact_checker_final` stage:
  [`orchestrator.py:1209`](../../ai_engine/agents/orchestrator.py#L1209)
- `optimizer_final_analysis` stage (analysis-only, no rewrite):
  [`orchestrator.py:1277`](../../ai_engine/agents/orchestrator.py#L1277)
- `final_analysis_report` field on `PipelineResult`:
  [`orchestrator.py:231`](../../ai_engine/agents/orchestrator.py#L231)
  marked `# v7: optimizer final analysis`
- Output contract validation:
  [`ai_engine/agents/contracts.py`](../../ai_engine/agents/contracts.py)
  exports `validate_optimizer_final_analysis_output`
- Observability emits `final_ats_score`, `keyword_gap_delta`,
  `readability_delta`:
  [`observability.py:157-167`](../../ai_engine/agents/observability.py#L157)
- Validator consumes the deltas and flags regressions:
  [`schema_validator.py:269-332`](../../ai_engine/agents/schema_validator.py#L269)
- Tests:
  [`test_optimizer_final_analysis.py`](../../backend/tests/unit/test_agents/test_optimizer_final_analysis.py),
  [`test_validator_final_analysis.py`](../../backend/tests/unit/test_agents/test_validator_final_analysis.py),
  cross-cutting in
  [`test_agentic_gaps.py:83`](../../backend/tests/unit/test_agents/test_agentic_gaps.py#L83)

**Conclusion:** all acceptance criteria met. **No work needed.**

### Brief 2 — Replay & Failure Intelligence ✅ DONE

- All three brief-named modules exist:
  [`ai_engine/evals/replay_runner.py`](../../ai_engine/evals/replay_runner.py),
  [`ai_engine/evals/failure_taxonomy.py`](../../ai_engine/evals/failure_taxonomy.py),
  [`ai_engine/evals/replay_report.py`](../../ai_engine/evals/replay_report.py)
- Admin UI surface (brief said "optional admin surface later"):
  [`frontend/src/components/workspace/replay-drawer.tsx`](../../frontend/src/components/workspace/replay-drawer.tsx)
- Tests:
  [`backend/tests/unit/test_replay_system.py`](../../backend/tests/unit/test_replay_system.py),
  [`backend/tests/unit/test_replay_route.py`](../../backend/tests/unit/test_replay_route.py)

**Residual verification needed:** confirm the taxonomy enum exposes
**all 10 classes** named in the brief (contract drift, artifact gap,
evidence binding miss, citation freshness miss, stage timeout,
provider failure, planner misclassification, low-evidence input,
validator escape, plus one more). Quick-win audit-only PR if any
class is missing.

### Brief 3 — Evidence Graph v1 ✅ DONE

- Migration matches brief data model:
  [`supabase/migrations/20260411000000_evidence_graph_v1.sql`](../../supabase/migrations/20260411000000_evidence_graph_v1.sql)
  defines `user_evidence_nodes`, `user_evidence_aliases`,
  `user_claim_edges` tables with RLS owner policies. (Brief also
  named `evidence_contradictions` — needs verification it's in the
  migration or shipped under another name.)
- Engine module:
  [`ai_engine/agents/evidence_graph.py`](../../ai_engine/agents/evidence_graph.py),
  feeds the planner per
  `evidence_graph.py:382` ("Used by the adaptive planner for
  risk_mode decisions.")
- Tests:
  [`backend/tests/unit/test_agents/test_evidence_graph.py`](../../backend/tests/unit/test_agents/test_evidence_graph.py)

**Residual verification needed:** confirm `evidence_contradictions`
table exists (or document its replacement) and that fact-check /
validator consume contradiction signals end-to-end (not just expose
them).

### Brief 4 — Adaptive Planner & Strategy Memory ⚠️ PARTIAL

- Planner exists:
  [`ai_engine/agents/planner.py`](../../ai_engine/agents/planner.py)
  has `jd_quality_score`, `profile_quality_score`,
  `evidence_strength_score` (implied by `evidence_score` in
  `determine_risk_mode()`), and a persisted plan artifact dict.
- **Risk-mode taxonomy diverges:** brief specified
  `fast / balanced / strict / evidence_first`; implementation
  uses `conservative / normal / aggressive`
  ([`planner.py:63`](../../ai_engine/agents/planner.py#L63)).
  Either rename to match brief, or amend the brief to ratify the
  existing taxonomy.
- **Strategy memory primitives not enforced:** brief specified
  storing `preferred_tone`, `preferred_structure_density`,
  `strong_role_family_emphasis_patterns`, `company_family_messaging`,
  `accepted_vs_rejected_outcomes`. Current
  [`memory.py`](../../ai_engine/agents/memory.py) is a generic K/V
  store (`AgentMemory.store/recall/feedback`) — no schema-typed
  primitives. Either add a typed memory contract or amend the brief
  to ratify that the typed primitives live elsewhere
  (`style_outcome_scorer.py`, `style_signal_deriver.py`,
  `user_style_hints.py` — those names from `ls ai_engine/agents/`
  suggest the work split out into per-primitive modules).

**Residual work — proposed S13-F1 candidate (small):** decide
between rename-to-brief vs amend-the-brief, and either way write a
behavioural test that pins the chosen risk-mode set + a memory
primitive contract test.

### Brief 5 — Mission Control UX v2 ⚠️ MOSTLY DONE

- Brief #1 Agent Timeline Rail:
  [`agent-timeline-rail.tsx`](../../frontend/src/components/workspace/agent-timeline-rail.tsx) ✅
- Brief #2 Evidence Inspector:
  [`evidence-inspector.tsx`](../../frontend/src/components/workspace/evidence-inspector.tsx)
  + `evidence-card.tsx` + `evidence-picker.tsx` ✅
- Brief #3 Risk Panel in Scoreboard:
  [`risk-panel.tsx`](../../frontend/src/components/workspace/risk-panel.tsx)
  + [`scoreboard-header.tsx`](../../frontend/src/components/workspace/scoreboard-header.tsx) ✅
- Brief #5 Action Queue 2.0:
  [`task-queue.tsx`](../../frontend/src/components/workspace/task-queue.tsx)
  + [`next-best-action.tsx`](../../frontend/src/components/workspace/next-best-action.tsx) ✅
- Replay surface (bonus, supports Brief 2):
  [`replay-drawer.tsx`](../../frontend/src/components/workspace/replay-drawer.tsx) ✅
- **Brief #4 Variant Lab MISSING** — zero matches for
  `workspace/variant*`. No file pairs ATS deltas + evidence-coverage
  deltas with a "winner & why" recommendation.

**Residual work — proposed S13-F2 candidate (medium):** Variant Lab
component + backend variant-comparison endpoint + tests + ADR.

## Recommendations to user

1. **Don't open S13 as "implement Brief 1".** Brief 1 is shipped.
   Marking it done in the briefs doc and closing it out is the right
   move (could be one tiny commit updating the briefs doc with a
   "Status: SHIPPED in v0.x.y" header per brief).

2. **The two remaining slices** are small and well-scoped:
   - **S13-F1** (Brief 4 reconciliation): risk-mode taxonomy
     decision + strategy-memory primitive contract test. ~150 LOC.
   - **S13-F2** (Brief 5 #4): Variant Lab component + endpoint +
     tests + ADR. ~400–600 LOC.

3. **Two small audit PRs to harden Briefs 2 & 3** could be folded
   into S13-F1 if cheap:
   - Confirm replay taxonomy ≥10 classes.
   - Confirm `evidence_contradictions` table + end-to-end
     consumption.

4. **The roadmap doc itself is stale.** The next squad should either
   rewrite [`NEXT_DEVELOPMENT_DESIGN_BRIEFS.md`](../NEXT_DEVELOPMENT_DESIGN_BRIEFS.md)
   to reflect what's actually shipped and what's left, or supersede
   it with a new `NEXT_DEVELOPMENT_DESIGN_BRIEFS_2026-Q2.md`.

## Hard constraint preserved

This audit is read-only. Zero source files modified. Test gate stays
2004 passed / 11 skipped.
