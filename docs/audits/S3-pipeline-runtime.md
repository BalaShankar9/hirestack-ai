# S3 — Pipeline Runtime · Audit

**Date**: 2026-04-28  
**Owner**: S3 Pipeline Runtime squad  
**Charter**: Make the orchestrator small, observable, and impossible to break.

## Surface area

| File | LOC | Responsibility |
|---|---|---|
| `backend/app/services/pipeline_runtime.py` | 3660 | The orchestrator: sinks, DatabaseSink, RuntimeConfig, PipelineRuntime, critic gates, persistence, evidence summary |
| `backend/app/services/event_bus_bridge.py` | 123 | Bridges `agent_events` ContextVar → runtime sink |
| `backend/app/services/progress_calculator.py` | 134 | Phase-weighted progress arithmetic |
| `ai_engine/agent_events.py` | n/a | ContextVar emitter for in-task events |

Existing test surface (10 files): `test_critic_gate_enforcement`, `test_critic_gate_hardening`, `test_evidence_ledger_integrity`, `test_persist_resilience`, `test_persist_to_document_library`, `test_phase2a_hardening`, `test_phase_critic_gates`, `test_phase_order_invariants`, `test_run_critic_gate`, `test_runtime_emitter_binding`.

## Risk inventory

| Class | Symbol | Why it matters | Coverage today |
|---|---|---|---|
| Sink wrapping | `_ExecutionPathTaggingSink` (L126-156) | Wraps the user-supplied sink to stamp `execution_path` on every event. Production dashboards trust this tag to detect degraded paths. `__getattr__` forwards to the inner sink — fragile if anyone reaches into `runtime.sink.events` / `iter_events`. | **None** |
| Persistence | `DatabaseSink.emit` (L243-330) | The only thing that turns an in-flight pipeline event into a row in `generation_job_events` AND keeps the `generation_jobs` row current. Polling clients depend on `current_agent`, `completed_steps`, `phase`, `progress`. | **None** |
| Persistence | `DatabaseSink._update_module_progress` (L416-445) | Writes throttled module-card progress to `applications.modules`. 5%-step throttle, only touches modules in `generating`/`queued` state. | **None** |
| Reporting | `PipelineRuntime._build_evidence_summary` (L3482-3514) | Aggregates evidence ledger + citation classification into the response envelope. Frontend evidence panel reads this. Defensive against missing/malformed inputs. | **None** |
| Phase ordering | `_PHASE_ORDER` / `_phase_index` / `completed_steps` arithmetic | DatabaseSink advances `completed_steps` only on phase change, taking max() to prevent regression. If a re-emit lands out-of-order, a wrong value can pin progress backwards. | Indirect via `test_phase_order_invariants` |
| Idempotency | Job restart path | Per blueprint: "no duplicate document_library rows on retry". `_persist_to_document_library` covered by Rank 15 test, but restart-after-partial is not. | Partial |
| Concurrency | dual-sink + asyncio.gather call sites | Per blueprint: "Replace asyncio.gather chains with a small structured-concurrency helper". Out of scope for hardening; tracked as scale-ask. | n/a |

## Fix queue

| # | Fix | Risk | LOC budget | Status |
|---|---|---|---|---|
| F1 | Behavioral tests for `_ExecutionPathTaggingSink` invariants (tagging, transparent forwarding, close-propagation) — locks the audit-tag contract before any decomposition. | High | ≤200 | planned |
| F2 | Behavioral tests for `DatabaseSink.emit` — event row written to `generation_job_events` with top-level columns populated; `progress` events update `generation_jobs` snapshot; redundant updates skipped; insert failure does not break pipeline. | High | ≤300 | planned |
| F3 | Behavioral tests for `_build_evidence_summary` — handles None, empty ledger, ledger with items, citation-classification counts, unlinked count. | Medium | ≤200 | planned |
| F4 | Behavioral tests for `DatabaseSink._update_module_progress` 5%-throttle + state-filter (only touches `generating`/`queued` modules). | Medium | ≤200 | planned |
| F5 | Extract `DatabaseSink` to `backend/app/services/pipeline/database_sink.py`. Pure move with re-export shim — no behavior change. Tests added in F2/F4 prove it. | High | ≤300 | planned |
| F6 | S3 sign-off doc + ADR-0005 on canonical-execution audit tag invariant. | Low | ≤150 | planned |

Each fix ships as one commit with its tests; suite must stay green and <15s.

## Out of scope (deferred to S3.5 / scale-asks)

- Full file decomposition into `phases/`, `sinks/`, `persistence/`, `finalize/` modules.
- `asyncio.gather` → structured-concurrency helper.
- Bounded SSE event queue / backpressure.
- Phase-level concurrency tuning for Atlas/Cipher fan-out.

These are larger structural changes that need their own squad cycle. The F1-F6 hardening lays the test scaffolding that makes them safe.
