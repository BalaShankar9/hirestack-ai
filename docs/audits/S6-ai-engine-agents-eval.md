# S6 — AI Engine Agents & Eval — Audit

**Squad**: S6 — AI Engine Agents & Eval
**Charter**: Agents are predictable, observable, and gated by a critic
that catches regressions before users see them.
**Surface area**: `ai_engine/agents/` (~12,919 LOC, 31 files),
`ai_engine/model_router.py` (438 LOC), `ai_engine/evals/` (~1,143 LOC).

## Existing Coverage

`backend/tests/unit/test_agents/` already holds 22 test files covering
orchestrator, base, eval, evidence_graph, lock, memory, schemas,
sub_agents, tools, trace, runtime_agents, citation contracts, critic
score differentiation, optimizer, validator. Plus root-level
`test_critic_gate_*` (3 files) and `test_phase_critic_gates.py`,
`test_run_critic_gate.py`, `test_agent_events.py`.

**Already well covered** → not in S6 scope:
- `agents/critic.py` (LLM judge inside gap_analysis pipeline).
- `agents/orchestrator.py` (1,776 LOC — covered by test_orchestrator + test_orchestrator_policy).
- `agents/eval.py`, `agents/evidence_graph.py`, `agents/tools.py`,
  `agents/sub_agents/`, `agents/memory.py`, `agents/lock.py`,
  `agents/schemas.py`, `agents/trace.py`, `agents/base.py`,
  `agents/optimizer.py`, `agents/validator.py` (via test_validator_final_analysis).

## S6 Surface — what S6 owns

Two files have **zero direct unit coverage** despite being in the
charter's named targets:

### F1 — `ai_engine/model_router.py` (438 LOC) — UNCOVERED

11 pure functions, security/cost-critical, no tests:

1. `_ModelHealth.record_success / record_failure / is_healthy / get_status` — auto-recovery state machine.
2. `resolve_model(task_type, default)` — 19 task types pinned to specific Gemini models.
3. `resolve_cascade(task_type, default)` — fallback ordering, health filtering, "all unhealthy" fallback.
4. `record_model_success / record_model_failure / get_model_health` — public health interface.
5. `available_task_types()` — surface lookup.
6. `record_quality_observation` (in-memory branch only — DB persist is best-effort).
7. `resolve_cost_optimized(task_type, min_quality, default)` — the smart cost optimizer (5+ observations gate, avg ≥ threshold, healthy check).
8. `get_cost_optimizer_stats()` — observability shape.
9. `reload_routes()` — env-var override pattern reset.
10. `estimate_task_complexity(task_type, input_tokens, requires_reasoning, requires_structured_output)` — complexity-driven routing.
11. `estimate_call_cost(model, input_tokens, output_tokens)` — USD cost math.

**Risk**: model routing is on the hot path of EVERY chain call. A
regression here either bills Pro for everything (cost blowout) or
routes Pro tasks to Flash (quality blowout). Cascade health filtering
also drives our outage resilience — if a model goes degraded and the
cascade doesn't filter it out, every call retries through the dead
model 3+ times before recovering.

### F2 — `ai_engine/agents/validation_critic.py` (240 LOC) — UNCOVERED

5 review modes per S6 charter ("Critic gates cover all 5 review
modes"), zero direct tests:

1. `review_benchmark(BenchmarkProfile)` — gates Stage 1.
2. `review_gap_map(SkillGapMap)` — gates Stage 2.
3. `review_documents(TailoredDocumentBundle, required_modules)` — gates document generation.
4. `review_final_pack(FinalApplicationPack)` — gates pipeline completion.
5. `review_plan(BuildPlan)` — gates planner output (DAG dependency check).

Plus internal scoring logic:
- `_finalize`: -25 per error, -5 per warning, floor at 0.
- `_gate_meta`: confidence floor 0.4, evidence tier floor INFERRED.
- `_tier_meets`: ordering UNKNOWN < USER_STATED < INFERRED < DERIVED < VERBATIM.
- `report_passed(report)`: passes iff zero error-severity findings.

**Risk**: this is THE gate that decides if a module transitions to
COMPLETED or FAILED. A drift here either lets bad output pass
(regression visible to users) or fails healthy output (false-negative
failure rate). The 5 review modes are the production_targets line
item from the squad charter directly.

## R-tagged risk inventory

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | Model routing drift (cost or quality blowout) | F1 — pin every task_type → model mapping, cascade ordering, health filtering |
| R2 | Critic gate drift (false pass / false fail) | F2 — pin all 5 review modes incl. fail conditions, scoring math, severity counting |
| R3 | Cost optimizer over/under-route | F1 — pin 5+ observations gate, threshold compare, health re-check |
| R4 | Eval harness silent break (gold corpus runner) | F3 — defer; eval runner already smoke-tested via test_eval.py |
| R5 | Schema enforcement on chain output (deferred from S5) | Out of S6 scope — needs a dedicated S-future on schemas/* + prompts/* |
| R6 | Per-tenant model overrides not tested | Out of S6 — the env-var override path is tested in F1; per-tenant is a feature not yet built |

## Fix Queue

- **F0** (this doc): audit + fix queue. No code change.
- **F1**: `test_model_router.py` — pin all 11 functions of model_router.py. ~50 tests, zero LLM calls.
- **F2**: `test_validation_critic.py` — pin all 5 review modes + scoring math + report_passed helper. ~30 tests, zero LLM calls (uses real artifact_contracts dataclasses).
- **F3**: ADR-0008 + S6 sign-off. Documentation.

Estimated 3 commits (F1, F2, F3) plus this F0. Suite stays under 8s.

## Out-of-S6 (deferred or already covered)

- Per-tenant model overrides (charter scale ask — feature not yet built).
- Cost telemetry attached to every agent invocation (separate squad — touches observability infrastructure).
- Eval datasets sparse for cover_letter, personal_statement (corpus expansion is content work, not contract pinning).
- `orchestrator.py` ~500 LOC dead branch review (already covered by test_orchestrator).
