# ADR 0015 — Planner risk_mode taxonomy and strategy-memory contract surface

**Status:** Accepted
**Date:** 2026-04-29
**Slice:** S13-F1
**Supersedes:** Brief 4 of
[`docs/NEXT_DEVELOPMENT_DESIGN_BRIEFS.md`](../NEXT_DEVELOPMENT_DESIGN_BRIEFS.md)
(only the parts about taxonomy naming and memory-primitive shape).

## Context

Brief 4 ("Adaptive Planner & Strategy Memory") in
`NEXT_DEVELOPMENT_DESIGN_BRIEFS.md` (2026-04-11) specified:

- a four-value risk-mode enum: `fast | balanced | strict | evidence_first`
- a typed strategy-memory contract storing `preferred_tone`,
  `preferred_structure_density`, `strong_role_family_emphasis_patterns`,
  `company_family_messaging`, `accepted_vs_rejected_outcomes`.

The reconciliation audit
([`docs/audits/S13-roadmap-reconciliation.md`](../audits/S13-roadmap-reconciliation.md))
found that the actually-shipped surface is:

- a three-value risk-mode enum:
  `conservative | normal | aggressive`
  ([`ai_engine/agents/planner.py:417-436`](../../ai_engine/agents/planner.py#L417))
  derived from average of `jd_quality_score`, `profile_quality_score`,
  `evidence_strength_score`.
- typed strategy primitives realised across
  [`style_signal_deriver.py`](../../ai_engine/agents/style_signal_deriver.py),
  [`style_outcome_scorer.py`](../../ai_engine/agents/style_outcome_scorer.py),
  [`user_style_hints.py`](../../ai_engine/agents/user_style_hints.py)
  rather than as one monolithic memory schema.

A decision is needed before any further work touches the planner.

## Decision

**1. Ratify the existing `conservative | normal | aggressive` enum.**
   Do NOT rename to `fast | balanced | strict | evidence_first`.

   Rationale:
   - The taxonomy parallels the existing `doc_variant.TONES =
     ["conservative", "balanced", "creative"]` surface
     ([`backend/app/services/doc_variant.py:14`](../../backend/app/services/doc_variant.py#L14))
     so users see one consistent vocabulary for "how cautious is this
     mode."
   - `evidence_first` is no longer a meaningful mode: post-Brief 3,
     every pipeline already routes through the evidence graph by
     default. Promoting it to a mode would be misleading.
   - `fast`/`strict` would conflate latency intent with quality
     intent — the existing `PipelinePlan.estimated_latency_hint`
     field already covers latency.
   - Renaming touches every test, every observability payload,
     every persisted `pipeline_plans` row. Cost > benefit.

**2. Ratify the distributed strategy-memory primitive surface.**
   Do NOT consolidate into a single typed memory contract.

   Rationale:
   - `style_signal_deriver` already extracts conservative style
     signals (tone, length, preferred_keywords) with explicit
     thresholds.
   - `style_outcome_scorer` already covers
     `accepted_vs_rejected_outcomes` semantics via per-outcome
     scoring.
   - `user_style_hints` already feeds the planner.
   - A single megaschema would force migrations on `agent_memory`
     and break the per-primitive evolution that's already working.

**3. Pin the enum with a contract test** so a future contributor
   can't silently expand the enum without a follow-up ADR.

## Consequences

### Positive

- Zero migrations.
- Zero observability payload churn.
- Zero rename PRs across `pipeline_plans` consumers.
- Brief 4 closed without code changes (only test + ADR).

### Negative / accepted

- The 2026-04-11 brief and the shipped behaviour now visibly
  diverge. Mitigation: status banner at top of
  `NEXT_DEVELOPMENT_DESIGN_BRIEFS.md` (commit `5bc7e60`) plus this
  ADR.
- A future "evidence_first" mode (e.g. for a high-stakes
  immigration / legal document pipeline) would need its own ADR.

## Test pin

[`backend/tests/unit/test_agents/test_planner_risk_mode_contract.py`](../../backend/tests/unit/test_agents/test_planner_risk_mode_contract.py)
asserts:

- `PlannerAgent.determine_risk_mode` returns one of the three
  ratified values for every score combination.
- The threshold mapping (avg ≥70 → aggressive, ≥40 → normal, else
  → conservative) is preserved.
- `PlanArtifact.to_dict()` round-trips the `risk_mode` value.

If a future change breaks any of those, this ADR must be revised
first.
