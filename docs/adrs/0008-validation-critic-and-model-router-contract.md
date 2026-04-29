# ADR-0008: Validation-Critic Gating and Model-Router Cost/Health Contract

**Status:** Accepted
**Date:** 2026-04-21
**Squad:** S6 — AI Engine: Agents & Eval
**Author:** Production-readiness blueprint executor
**Supersedes:** —
**Superseded-by:** —

---

## Context

The agent pipeline is built on two unsweepable hot paths:

1. **`ai_engine/model_router.py`** — every chain invocation hits
   `resolve_model()` to pick a Gemini tier and `resolve_cascade()` for
   fallbacks. A regression here either over-bills (Pro for everything)
   or under-quality routes (Flash for tasks needing Pro reasoning).
   Health filtering in `resolve_cascade` decides whether a degraded
   model hammered three times in a row gets re-tried in the next call
   — drift here multiplies the latency budget per call.

2. **`ai_engine/agents/validation_critic.py`** — every stage transition
   from RUNNING → COMPLETED runs through the matching `review_*`
   method. The pass/fail decision (`report_passed`) is a binary gate
   on the user-visible pipeline. False positives ship bad documents;
   false negatives block valid completions.

Pre-S6 state:

- model_router had **zero direct tests**. Existing chain tests
  exercised `resolve_model` indirectly by smoke-running entire chains
  — never asserting per-task routing.
- validation_critic had **zero direct tests**. Existing pipeline tests
  asserted "stage X completed" but never asserted *why* the critic
  passed or what would have failed it.

Outcome: any refactor of these two files (e.g. adding new task types,
reworking the cost optimizer, reshaping ValidationFinding) ships
without a single failing test — the pipeline only catches the
regression in production.

## Decision

We pin **two contracts** with full behavioural test coverage. These
contracts are now load-bearing — changes to either file must update
the corresponding test suite first.

### Contract A — Model Router

1. **`resolve_model(task_type, default)` is a pure function from a
   fixed task vocabulary to a Gemini tier.**
   - 19 task types are public surface (see
     `available_task_types()`):
     - **Pro tier**: `reasoning`, `fact_checking`, `quality_doc`.
     - **Flash tier**: `research`, `structured_output`, `optimization`,
       `creative`, `drafting`, `critique`, `synthesis`, `validation`,
       `general`, `brief_computation`.
     - **2.0-Flash tier**: `extraction`, `classification`, `fast_doc`,
       `summarization`, `formatting`.
   - `brief_computation` is the only intentional exception to the
     "lives in tier-3 block but routes to 2.5-flash" rule.
   - `None`, `""`, and unknown task types fall through to the
     caller-supplied default.
   - Env-var overrides (`MODEL_ROUTES`) merge with defaults; invalid
     JSON or non-dict values are silently ignored (never raised).

2. **`resolve_cascade(task_type, default)` always appends the default
   to the cascade tail unless it is already in the list, then
   filters out unhealthy models.**
   - If filtering removes everything, return the **unfiltered** list
     as a last-resort fallback (the all-unhealthy branch).
   - Cascade env-var override (`MODEL_CASCADE`) merges per-task.

3. **`_ModelHealth` is a self-healing failure counter:**
   - `FAILURE_THRESHOLD = 3`. At-or-above → unhealthy.
   - `RECOVERY_TIMEOUT = 120s`. After timeout → re-probe (returns
     healthy) until next failure resets the counter.
   - `record_success` clears the failure count.
   - `get_status()` only emits entries with non-zero failures.

4. **`resolve_cost_optimized` requires ≥5 quality observations
   before recommending a cheaper model**, and re-checks health
   immediately before recommending. The rolling window is capped at
   `_MAX_OBSERVATIONS = 50` per (task, model) pair.

5. **`estimate_call_cost` uses the per-tier USD constants and
   defaults unknown models to Pro pricing** (a safe over-estimate).

6. **`_persist_quality_observation` is best-effort** — DB import or
   write failures must NEVER raise into the caller's path. (Tested
   by mocking the persist function.)

### Contract B — Validation Critic

1. **All 5 review modes are public surface and return a
   `ValidationReport` with the standard scoring contract:**
   - `review_benchmark(BenchmarkProfile | None)`
   - `review_gap_map(SkillGapMap | None)`
   - `review_documents(TailoredDocumentBundle | None, required_modules=None)`
   - `review_final_pack(FinalApplicationPack | None)`
   - `review_plan(BuildPlan | None)`

2. **`None` artifacts always emit a single error-severity finding
   with rule `<mode>.missing`** — never raise, never crash.

3. **`overall_score = max(0, 100 - 25 × errors - 5 × warnings)`.**
   The score is a function of finding severity, period.

4. **`_gate_meta` is run on every artifact:**
   - `confidence < 0.4` → warning `meta.low_confidence`.
   - `evidence_tier` weaker than `INFERRED` → warning
     `meta.weak_evidence`.
   - Tier ordering: `VERBATIM > DERIVED > INFERRED > USER_STATED > UNKNOWN`.

5. **`report_passed(report)` is the single source of truth for
   gate decisions:**
   - `None` report → `False`.
   - Any `error`-severity finding → `False`.
   - `warning` and `info` findings do not fail the gate.

6. **`required_modules` in `review_documents` is normalised
   case-insensitively** so callers can pass `"CV"` or `"cv"`
   interchangeably.

7. **`failed_modules` error messages in `review_final_pack` are
   truncated to 200 characters.** This prevents the report from
   ballooning when an LLM returns a multi-thousand-character error
   blob.

## Consequences

**Positive**

- 94 new tests (53 model_router + 41 validation_critic). Every
  contract item above has at least one assertion.
- Future refactors of routing math or critic heuristics will surface
  contract changes immediately, before the chain pipeline is touched.
- Cost-optimizer regressions (the highest-impact silent regression
  category — wrong model = wrong unit economics) are caught by the
  per-model and per-task-type pinning.

**Negative**

- The 19-task-type list is now load-bearing — adding a new task type
  requires both updating `_DEFAULT_ROUTES` AND adding it to
  `available_task_types`/test pinning.
- The `_ModelHealth` failure threshold of 3 and recovery timeout
  of 120s are now contract — tuning these requires updating tests.
- `_finalize` arithmetic (25/error, 5/warning) is contract; changing
  the weighting requires updating `TestScoringMath`.

## Verification

- `backend/tests/unit/test_model_router.py` — 53 tests, all pure
  logic, ~0.16s runtime, zero LLM calls, zero DB calls.
- `backend/tests/unit/test_validation_critic.py` — 41 tests, all
  pure logic, ~0.22s runtime, zero LLM calls, zero DB calls.
- Suite total: 1552 passed in 6.47s. Suite latency budget unchanged.

## References

- ADR-0007: Chain output and construction contract (S5).
- `docs/audits/S6-ai-engine-agents-eval.md` — original gap audit.
- `docs/audits/S6-ai-engine-agents-eval-signoff.md` — squad close-out.
- `ai_engine/model_router.py` — pinned surface.
- `ai_engine/agents/validation_critic.py` — pinned surface.
