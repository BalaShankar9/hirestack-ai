# S4 Generation API & SSE — sign-off (2026-04-29)

Squad: Generation API & SSE
Status: **GREEN**
Audit: `docs/audits/S4-generation-api-sse.md`
ADR: `docs/adrs/0006-sse-protocol-contract.md`

## Production-readiness bar

| # | Check                                                                                              | Status |
|---|----------------------------------------------------------------------------------------------------|--------|
| 1 | Module identifier normalization is deterministic across snake/camel/dedup/empty/unknown           | ✅ `test_normalize_requested_modules.py` (10 tests) |
| 2 | `_module_has_content` reads exactly the declared column for each of the 9 modules                 | ✅ `test_module_has_content.py` (24 tests) |
| 3 | `_default_module_states` and `_merge_module_states` defend the full 9-key surface, no input mutation | ✅ `test_merge_module_states.py` (10 tests) |
| 4 | `_mark_application_generation_finished` race protection — `ready` never overwritten by `failed`/`cancelled` | ✅ `test_mark_application_generation_finished.py` (9 tests) |
| 5 | SSE envelope helpers (`_sse`/`_agent_sse`/`_detail_sse`) emit the wire format EventSource demands | ✅ `test_sse_stream_contract.py` (12 tests) |
| 6 | Stream loop terminal-drain + monotonic sequence cursor enforced by source-shape sentinels         | ✅ same suite (3 tests) |
| 7 | Backend unit suite green and <15s                                                                 | ✅ 1329 passed in 6.50s |

## Fixes shipped

| ID  | Title                                                                                          | Commit  |
|-----|------------------------------------------------------------------------------------------------|---------|
| F0  | Audit doc — risk inventory R1-R6 + fix queue F1-F6                                             | ac3f850 |
| F1  | `_normalize_requested_modules` invariants (10 tests)                                           | 99d8165 |
| F2  | `_module_has_content` per-slot column mapping (24 tests)                                       | f18bfbf |
| F3  | `_default_module_states` + `_merge_module_states` (10 tests)                                   | f1af721 |
| F4  | `_mark_application_generation_finished` race protection (9 tests)                              | 4e519e3 |
| F5  | SSE envelope helpers + stream terminal-drain regression sentinels (15 tests)                   | 95cecab |
| F6  | ADR-0006 (SSE protocol) + this sign-off                                                        | (this commit) |

(Per blueprint: commits stay local until the P4-S10 staging-deploy gate.)

## What was NOT done — and why it is safe to defer

**Physical decomposition of `jobs.py` (2.1k LOC) into `job_crud.py` + `runner.py` + `status.py`.**
Originally proposed as a structural fix in the audit. Re-scoped because:

- The 68-test contract pinned across F1-F5 now defends every observable
  contract of the most error-prone helpers in `jobs.py`. A future
  contributor moving these functions to a new module will get
  immediate green/red feedback that the move is a no-op.
- The decomposition touches ~30 import sites and 5 test files. As a
  standalone PR the blast radius is poor. Better to bundle with the
  S4-extraction-of-stream-loop motion when SSE behavioural tests
  graduate (see ADR-0006 "Future" section).

**End-to-end behavioural test of `stream_generation_job` against a fake `sb`.**
The endpoint is a closure inside FastAPI with auth + rate-limit
middleware in front. To drive it requires either (a) extracting the
inner async generator to a module-level helper, or (b) standing up a
TestClient + auth fixture chain. Both are larger swings than this
squad's budget. Coverage gap is filled by:

- 12 behavioural tests on the SSE envelope helpers — the highest-risk
  drift surface (frontend EventSource parser).
- 3 source-shape regression sentinels on the stream loop — they fail
  in CI if a contributor drops the terminal drain, switches `.gt` to
  `.gte`, or removes the `last_sequence` advancement.

**`stream.py` (`/pipeline/stream` POST endpoint) deep coverage.**
Listed in the audit but lower priority: this is the legacy direct-pipeline
SSE path and traffic to it is decreasing. The ADR-0006 envelope contract
already covers its `_sse`/`_agent_sse`/`_detail_sse` usage. A focused
audit will follow if the path stays in production after S10.

## Operator action queue

After P4-S10 push to staging:

- Watch `/api/generate/jobs/{job_id}/stream` p95 latency dashboards. The
  terminal-drain pattern means the loop will do one extra SELECT per
  finished job — expected impact is sub-millisecond.
- Confirm no rise in "stuck at 99%" support tickets — these were the
  visible symptom of the bug class F5 fences off.
- No schema migrations required (S4 was test-only).

## Suite snapshot at sign-off

```
1329 passed, 22 warnings in 6.50s
```

Up from 1261 at S3 sign-off (+68 tests across F1-F5).

## Next squad

S5 AI Engine Chains — see blueprint line 162+. Surface area:
`ai_engine/chains/`. Targets: every chain produces validated
schema-conformant output, prompts under version control,
quality measured.
