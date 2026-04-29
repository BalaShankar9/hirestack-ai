# ADR-0007: AI Engine Chain Output & Construction Contract

**Status**: Accepted
**Date**: 2026-04-21
**Squad**: S5 — AI Engine Chains
**Supersedes**: —
**Superseded by**: —

## Context

`ai_engine/chains/` hosts 22 prompt chains (~7,174 LOC) that wrap LLM calls
behind structured Python interfaces. Each chain mediates between an
unreliable model (LLMs hallucinate keys, return strings instead of dicts,
omit required fields, embed XSS vectors) and downstream systems that
assume a fixed shape (Supabase schema, frontend gauges, exporters).

Three drift surfaces threatened the platform before S5:

1. **`_validate_result` last-line normalisers** — 7 chains carry a
   defensive validator that backfills missing keys with safe defaults.
   Adding a key to a chain's prompt without adding its default to
   `_validate_result` is a silent production bug (next caller hits a
   `KeyError`).
2. **Construction surface** — the service layer constructs every chain
   through `__init__(ai_client)`. If a chain renames the kwarg or adds
   a required positional, the platform fails at startup.
3. **Pure-helper utility belt** — the resume-parsing helpers
   (`_clean_resume_text`, `_normalize_date`, `_clean_skill`, etc.) and
   the validator security primitives (`sanitize_content`,
   `check_for_fabrication`) are pure but had zero coverage. Drift in
   `sanitize_content` silently re-opens an XSS vector.

## Decision

We pin the following contracts as load-bearing:

### 1. `_validate_result(result: dict) -> dict`

Every chain whose `analyze_*` / `generate_*` / `parse_*` method ends
with this normaliser MUST:

- **Backfill every persisted key** with a typed default (empty list,
  empty dict, sentinel string, or `None`). The output schema is the
  union of all keys the persistence/UI layers read.
- **Clamp numeric fields** to their valid range when present
  (`compatibility_score ∈ [0, 100]`).
- **Drop malformed list entries** rather than crash
  (recommendations that arrive as bare strings are filtered out).
- **Tolerate `None` / non-dict input** (LLM wrappers occasionally
  return a list or string when they fail; validator must reset to
  defaults rather than `AttributeError`).

Behavioural pin: `backend/tests/unit/test_chain_validate_result.py` and
`backend/tests/unit/test_role_profiler_helpers.py`.

### 2. Construction surface — `__init__(self, ai_client)`

Of the 20 exported LLM chains, **19 follow the standard
`__init__(self, ai_client)` signature**.

`DocumentPackPlanner` is the **sole** allowed exception
(`__init__(self, ai_client, catalog)`) because the planner needs the
catalog at construction time for cache locality.

Adding any further exception requires:
- A documented architectural reason in the chain's docstring.
- Updating the `_NON_STANDARD_INIT` allowlist in
  `backend/tests/unit/test_chain_construction_surface.py`.
- Updating this ADR.

Every chain MUST also expose **at least one async public method** —
LLM chains run on the asyncio executor; a sync-only chain would block
the event loop.

Behavioural pin: `backend/tests/unit/test_chain_construction_surface.py`
(52 tests, parametrised).

### 3. Pure-helper testability

Helpers that don't touch `ai_client` are tested **without** mocking AI
calls. Construct via `Chain(ai_client=object())` or
`Chain(MagicMock())` and call helpers directly. Pure helpers MUST stay
pure (no `await`, no I/O); drift to async breaks the test pattern.

Targeted helpers under contract:

- `RoleProfilerChain`: `_clean_resume_text`, `_is_noise_line`,
  `_normalize_date`, `_clean_skill`, `_deduplicate_skills`,
  `_compute_parse_confidence`, `_build_parse_warnings`, `_sort_by_date`.
- `CompanyIntelChain._minimal_fallback` (security-sensitive last-resort).
- `ValidatorChain.sanitize_content` (XSS surface),
  `validate_json_structure`, `check_for_fabrication`.

## Consequences

### Positive

- 109 new behavioural tests across the AI engine (F1: 36, F2: 21,
  F3: 20, F4: 52) wired into the unit suite. Suite stays under 8s.
- Adding a new key to a chain's persisted output is now a 2-step
  operation: prompt change + `_validate_result` default. The test
  suite catches the omission immediately.
- XSS sanitiser drift fails CI (regression of any of script tag,
  `on*` event handler, or `javascript:` URI is caught).
- Adding a new chain via constructor refactor (`client=` instead of
  `ai_client=`) fails the parametrised contract test.

### Negative

- The `_NON_STANDARD_INIT` allowlist is a tripwire — any future chain
  needing a custom constructor must explicitly justify the exemption.
- The 20-chain export count is locked; adding/removing a chain
  requires updating both the contract test and the audit doc.

## Future

- **Schema enforcement (R5)**: 7 JSON schemas exist in
  `ai_engine/schemas/` but are not yet enforced against
  `_validate_result` output. Bundle into S6 alongside prompt
  versioning (move embedded prompts to `ai_engine/prompts/`).
- **Construction-time chain registry**: a single factory module
  `ai_engine.chains.registry` would close the construction surface
  entirely (chain name → instance). Currently the service layer
  constructs ad-hoc; centralising would let the registry enforce the
  `_NON_STANDARD_INIT` allowlist at runtime, not just test-time.
- **`_validate_result` schema generation**: defaults could be derived
  from the JSON schema instead of hand-maintained. Defer until R5
  schemas are wired in.
