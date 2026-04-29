# ADR-0016: Variant Lab — deterministic winner pick + AI reasoning

**Date:** 2026-04-29  
**Status:** Accepted  
**Slice:** S13-F2  
**Supersedes:** none  
**Related:** ADR-0015 (planner risk_mode), Brief 5 #4 of `docs/NEXT_DEVELOPMENT_DESIGN_BRIEFS.md`

---

## Context

Brief 5 #4 of the development design briefs called for the A/B Doc Lab
to "pair ATS deltas + evidence-coverage deltas with a 'winner & why'
recommendation." The shipped surface (S13-F0 audit, commit `e8570b8`)
was already ~70% there:

- `frontend/src/app/(dashboard)/ab-lab/page.tsx` — full 3-variant UI
- `backend/app/api/routes/variants.py` — `/api/variants/generate`
- `backend/app/services/doc_variant.py` — `DocVariantService`
- `ai_engine/chains/doc_variant.py` — `DocumentVariantChain.generate_variant`
- `doc_variants` Supabase table with `ai_analysis` JSONB column

But the F0 audit also surfaced two bugs and one gap:

1. **Bug A:** `DocVariantService.generate_variants` calls
   `chain.compare_variants(...)` — a method that **did not exist** on
   `DocumentVariantChain`. Any production call to `/api/variants/generate`
   would raise `AttributeError` after the per-tone variants were saved.
2. **Bug B:** The same service called
   `chain.generate_variant(original_content=...)` but the chain method's
   parameter is `document_content`. The kwarg silently slid into
   `**kwargs` and the `document_content` positional default ("") meant
   the chain prompted on an empty source.
3. **Gap:** No evidence-coverage scoring, no system-recommended winner,
   no "why" reasoning.

We needed to fix both bugs and close the gap in one slice without
adding a Supabase migration (the existing `ai_analysis JSONB` column
absorbs the new fields).

---

## Decision

### 1. Winner is picked deterministically; the AI only writes the *why*

`DocumentVariantChain.compare_variants(...)` scores each variant with
three pure functions:

| Metric | Heuristic | Weight in composite |
| --- | --- | --- |
| `evidence_coverage` | % of distinct job-title keywords present | **0.45** |
| `ats_score` | 50 baseline + keyword coverage + length sanity, clamped 0-100 | **0.35** |
| `readability_score` | Flesch-style sentence-length penalty, 0-100 | **0.20** |

The variant with the highest weighted composite wins. Period.

The LLM is then asked, in a separate prompt, to write 1-2 sentences
explaining **why** the already-chosen winner suits the role. The prompt
explicitly forbids the LLM from picking a different winner. Test
`test_compare_variants_ai_cannot_override_score_pick` pins this
contract: even when the mock LLM returns reasoning that says "Actually,
conservative is better", the score-picked winner stands.

**Why deterministic:** A/B Lab is a *decision-support* tool. Users need
to trust that the same input yields the same recommendation. An LLM
that can flip the winner makes the tool non-reproducible and
non-auditable. Reasoning text is the right place for LLM creativity;
the pick is not.

### 2. Weights favour evidence over ATS over readability

`evidence_coverage 0.45 > ats_score 0.35 > readability_score 0.20`
because:

- Brief 3 made evidence-grounding the platform's differentiator;
  picking a variant that *demonstrates more of the role's evidence
  surface* matters most.
- ATS is table-stakes — important but not differentiating once the
  variant clears a baseline.
- Readability is a tiebreaker. A document that wins on coverage and
  ATS but is mildly less readable still wins; readability alone
  shouldn't override the other two.

Weights live in module-level constant `WINNER_WEIGHTS` in
`ai_engine/chains/doc_variant.py` and are pinned by
`test_composite_weights_sum_to_one`.

### 3. Ties broken by input order

If two variants have identical composite scores, `max()` over a dict
returns the first key in insertion order (Python 3.7+ contract). This
means the **caller's** tone ordering controls the tiebreak. The service
calls with `["conservative", "balanced", "creative"]`, so `conservative`
wins ties — matching the conservative-bias most regulated industries
expect.

### 4. AI failure is non-fatal

If `client.complete_json` raises or returns empty, the winner is still
picked and a deterministic fallback blurb is returned. No 500 to the
user just because the reasoning LLM hiccuped. Pinned by
`test_compare_variants_reasoning_failure_falls_back_to_blurb`.

### 5. Bug A fix: implement `compare_variants` (this ADR)

The method now exists on `DocumentVariantChain` with the signature:

```python
async def compare_variants(
    self,
    variants: dict[str, str],     # {tone: content}
    job_title: str = "",
    company: str = "",
    job_keywords: list[str] | None = None,
    original_content: str = "",   # used to compute delta_vs_original
) -> dict
```

Returns `{comparison: [...], winner: {variant, composite_score, reasoning, weights}, weights}`.

### 6. Bug B fix: `original_content` accepted as alias

`generate_variant` now accepts both `document_content` and the legacy
`original_content` kwarg. Pinned by
`test_generate_variant_accepts_original_content_alias`.

### 7. No new Supabase migration

`evidence_coverage`, `composite_score`, `delta_vs_original`, and
`winner_reasoning` are all stored inside the existing `ai_analysis`
JSONB column on `doc_variants`. The boolean `is_selected` is repurposed
to mark the system-recommended winner at generation time; users can
still override via `PUT /api/variants/{id}/select` and the override
remains the source of truth.

---

## Alternatives considered

### A. Let the LLM pick the winner directly

Rejected. Non-deterministic, non-auditable, and gives the LLM a way to
silently disagree with the heuristic scores it was just shown. Users
would lose trust the first time the tool flipped a recommendation
between identical runs.

### B. Weight ATS > evidence > readability

Rejected. ATS is a vendor surface; evidence-coverage is the platform's
differentiator (Brief 3). Optimising for the keyword scanner instead
of the role's actual evidence surface would undo the work S13-F0
ratified.

### C. Add a new `variant_comparisons` Supabase table

Rejected for this slice. The existing `ai_analysis` JSONB absorbs
every new field with zero migration risk. If we later need to query
across comparisons (e.g. "show me all variants where evidence_coverage
exceeded the original by ≥20 points"), promoting fields to columns is
a follow-up ADR — not blocking F2.

### D. Compute `evidence_coverage` against the full evidence graph

Tempting but out of scope for F2. The full graph requires an
`application_id` plus a researcher pass. The current heuristic uses
job-title tokens as a proxy; callers can pass a richer
`job_keywords=` list when they have one. Future ADR can wire the full
graph in without changing the public chain signature.

---

## Consequences

**Positive**

- Two production bugs in `/api/variants/generate` fixed.
- Brief 5 #4 closed: deltas, evidence-coverage, system winner,
  AI-generated "why" all shipped.
- Behaviour is fully deterministic except for one bounded LLM string;
  reproducible recommendations earn user trust.
- No Supabase migration → instant rollout, instant rollback.

**Negative**

- `evidence_coverage` is a job-title-keyword proxy, not the full
  evidence graph (see Alternative D). Surface this in the UI tooltip
  so users don't over-read the metric.
- Composite weights are opinionated. A future product decision to
  rebalance (e.g. for industries that weight readability higher)
  requires either a per-org override or a new ADR.

**Neutral**

- `WINNER_WEIGHTS` is a module-level constant; tests pin it so accidental
  drift fails CI.

---

## Implementation pointers

- `ai_engine/chains/doc_variant.py` — `compare_variants`, `_ats_score`,
  `_readability_score`, `_keyword_density`, `_composite`,
  `WINNER_WEIGHTS`, `_winner_reasoning`, `_fallback_reasoning`.
- `backend/app/services/doc_variant.py` — calls `compare_variants` with
  `original_content=`, persists winner + evidence_coverage + composite
  + delta into `ai_analysis` JSONB.
- `backend/tests/unit/test_chains/test_doc_variant_compare.py` — 16
  contract tests pinning every clause of this ADR.
- `frontend/src/app/(dashboard)/ab-lab/page.tsx` — system-winner
  banner + per-variant evidence_coverage chip + delta display.

---

## How to revise this ADR

If a future slice wants to:

- change `WINNER_WEIGHTS`,
- let the LLM pick the winner,
- add new metrics into the composite,
- swap the keyword heuristic for the full evidence graph,

it must:

1. Open ADR-00xx superseding (in part) ADR-0016.
2. Update `test_composite_weights_sum_to_one` and the weight-balance
   tests.
3. Update `test_compare_variants_ai_cannot_override_score_pick` only
   if the LLM-as-arbiter rule itself is being changed.
