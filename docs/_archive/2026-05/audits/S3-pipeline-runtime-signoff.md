# S3 Pipeline Runtime — sign-off (2026-04-28)

Squad: Pipeline Runtime
Status: **GREEN**
Audit: `docs/audits/S3-pipeline-runtime.md`
ADR: `docs/adrs/0005-pipeline-execution-path-audit-tag.md`

## Production-readiness bar

| # | Check                                                                                          | Status |
|---|------------------------------------------------------------------------------------------------|--------|
| 1 | Every emitted event carries an `execution_path` audit tag                                      | ✅ ADR-0005; tagging-sink is unconditional in `PipelineRuntime.__init__` |
| 2 | DatabaseSink event-row schema (top-level cols + payload) pinned by behavioral tests            | ✅ `test_database_sink_emit.py` (7 tests) |
| 3 | DatabaseSink job-snapshot dedup, sequence-number monotonicity, and complete-event finalization | ✅ same suite |
| 4 | Module-progress writer 5%-throttle and state-filter (don't overwrite completed/failed)         | ✅ `test_database_sink_module_progress.py` (6 tests) |
| 5 | Phase metadata internal consistency — `_PHASE_ORDER` ↔ `_PHASE_STEP` ↔ `_phase_to_agent` ↔ `_TOTAL_STEPS` | ✅ `test_phase_metadata_consistency.py` (7 tests) |
| 6 | Evidence summary builder (`_build_evidence_summary`) covers ledger + citations + edge cases    | ✅ `test_build_evidence_summary.py` (8 tests) |
| 7 | Backend unit suite green and <15s                                                              | ✅ 1261 passed in 6.14s |

## Fixes shipped

| ID  | Title                                                                              | Commit  |
|-----|------------------------------------------------------------------------------------|---------|
| F1  | `_ExecutionPathTaggingSink` invariants pinned (7 tests)                            | (pending push) |
| F2  | DatabaseSink.emit row schema + dedup + sequencing pinned (7 tests)                 | (pending push) |
| F3  | `_build_evidence_summary` ledger/citation merge pinned (8 tests)                   | (pending push) |
| F4  | `_update_module_progress` 5%-throttle + state-filter pinned (6 tests)              | d14c163 |
| F5  | Phase metadata internal-consistency invariants (7 tests)                           | ae11860 |
| F6  | ADR-0005 + this sign-off                                                           | (this commit) |

(Per blueprint: commits stay local until the P4-S10 staging-deploy gate.)

## What was NOT done — and why it is safe to defer

**Physical extraction of `DatabaseSink` to `backend/app/services/pipeline/database_sink.py`.**
Originally proposed as F5. Re-scoped because:

- The 35-test contract (F1+F2+F3+F4+F5) now pins every observable behavior of `DatabaseSink` and the runtime's event-tagging guarantee. Any future move can be verified as a no-op move by running the suite.
- The extraction has high import-site blast radius (`jobs.py`, `helpers.py`, three test files, `event_bus_bridge.py` doc strings) for ~240 LOC of net code movement. The leverage is poor as a standalone PR.
- A bigger structural refactor is planned in S4 (Generation API & SSE) — extracting all sinks together at that point will be cleaner than DatabaseSink in isolation.

**SLO budget warnings on phase timing.**
Listed as a long-term goal in the squad blueprint. Not a P0 — current observability is sufficient via the `latency_ms` column on `generation_job_events` plus the dashboards built on it. Will revisit once a real SLO budget is published.

**`_legacy_pipeline_allowed()` toggle removal.**
The legacy path stays behind the env-var gate until production telemetry shows the agent path serving 100% of traffic for a sustained window (per ADR-0005 closing argument). Removal is a P4-S10-or-later motion.

## Operator action queue

After P4-S10 push to staging:

- Watch the `execution_path` partition on `generation_job_events.payload`. Expected: `agent` ≈ 100%, `legacy` ≈ 0%, `unknown` = 0.
- Confirm the new event-row top-level columns (`agent_name`, `stage`, `status`, `latency_ms`, `sequence_no`) are populated for every fresh job — these are what the live agent dock reads.
- No schema migrations required (S3 was test-only fixes).

## Suite snapshot at sign-off

```
1261 passed, 23 warnings in 6.14s
```

Up from 1226 at S2 sign-off (+35 tests across F1-F5).

## Next squad

S4 Generation API & SSE — see blueprint lines 135-159. Surface area:
`backend/app/api/routes/generate/jobs.py` (~2.1k LOC),
`stream.py` (~1k LOC), `helpers.py` (~1.2k LOC).
