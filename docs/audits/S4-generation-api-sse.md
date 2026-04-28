# S4 Pipeline — Generation API & SSE — audit (2026-04-29)

Squad: Generation API & SSE
Status: in flight

## Surface area

```
backend/app/api/routes/generate/
  jobs.py            2336 LOC   ← largest file in the repo
  stream.py          1029 LOC
  helpers.py         1076 LOC
  sync_pipeline.py    456 LOC
  cv_variants.py      173 LOC
  document.py         183 LOC
  planned.py          131 LOC
  schemas.py           93 LOC
  __init__.py          71 LOC
```

`jobs.py` carries 7 routes, the durable job runner (3 layers deep —
`_run_generation_job` → `_run_generation_job_inner` →
`_run_generation_job_inner_runtime[_body]`), the in-process scheduler,
and three lifecycle cleanup functions. `stream.py` carries the
ad-hoc SSE pipeline endpoint. `helpers.py` is the shared utility
catch-all (SSE framing, validation, `finalize_job_status_payload`).

## Existing test coverage

| Helper / endpoint                          | Tests                                         |
|--------------------------------------------|-----------------------------------------------|
| `finalize_job_status_payload`              | `test_finalize_job_status_shared.py` ✅      |
| `_apply_preferred_lock`                    | `test_apply_preferred_lock.py` ✅            |
| Module whitelist enforcement               | `test_module_whitelist_enforcement.py` ✅    |
| Runtime emitter binding                    | `test_runtime_emitter_binding.py` ✅         |
| Lifecycle hardening (cleanup queries)      | `test_lifecycle_hardening.py` ✅             |
| `_normalize_requested_modules`             | **none**                                      |
| `_module_has_content`                      | **none**                                      |
| `_merge_module_states` / `_default_…`      | **none**                                      |
| `_mark_application_generation_finished` race protection | **none** (semantics matter — protects ready→error overwrite) |
| `/jobs/{job_id}/stream` sequence-monotonicity + terminal drain | **none** |

## Risk inventory

| #  | Behavior at risk                                                             | Why it matters                                                                                                   | Severity |
|----|------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|----------|
| R1 | Module-key normalization (`snake_case` ↔ `camelCase`)                       | Frontend posts camelCase, internal callers use snake_case. A drift here drops modules silently from generation. | High     |
| R2 | `_module_has_content` per-key column mapping                                 | Drives "skip already-generated" optimisation in retries; wrong mapping triggers redundant generation or, worse, skips real-empty modules. | High |
| R3 | `_merge_module_states` defaulting                                            | Ensures every job sees all 9 module slots even when application row carries a sparse `modules` dict. Frontend module-cards crash on missing keys. | Medium |
| R4 | `_mark_application_generation_finished` ready→error race                     | A failed job MUST NOT overwrite a `ready` module from a concurrent successful job. Currently coded but untested. | High     |
| R5 | SSE stream — sequence-no monotonicity, terminal-state drain, idle keepalive  | Lost events between the "got terminal status" check and the final SELECT cause clients to miss the `complete` event. | High |
| R6 | SSE protocol — undocumented event-name set, retry semantics, downgrade rules | Future contributors invent new event names that frontend doesn't know about. ADR-0006 will codify.              | Medium   |

## Fix queue

| ID | Title                                                                                                          | Severity | Budget LOC | Status |
|----|----------------------------------------------------------------------------------------------------------------|----------|------------|--------|
| F1 | Pin `_normalize_requested_modules` invariants — snake/camel mapping, dedup, unknown rejection, empty→default. | High     | ≤200       | planned |
| F2 | Pin `_module_has_content` per-key column mapping for all 9 module slots.                                      | High     | ≤200       | planned |
| F3 | Pin `_default_module_states` + `_merge_module_states` defaulting / merge precedence.                           | Medium   | ≤150       | planned |
| F4 | Pin `_mark_application_generation_finished` race protection — ready never downgrades on a failed/cancelled run. | High   | ≤300       | planned |
| F5 | Pin `/jobs/{job_id}/stream` sequence-monotonicity + terminal-state drain via the underlying SSE polling loop. (Test-only — extract the inner loop into a pure async helper if needed for testability.) | High | ≤400 | planned |
| F6 | ADR-0006 (SSE protocol contract) + S4 sign-off.                                                                | Low      | ≤200       | planned |

Per blueprint: ≤500 LOC per commit, ≥1 behavioral test per fix, suite
stays green and <15s, commits stay local until P4-S10 staging gate.
