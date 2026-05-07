# S5 Sign-Off — AI Engine Chains

**Squad**: S5 — AI Engine Chains
**Status**: ✅ COMPLETE GREEN
**Date**: 2026-04-21
**Suite**: 1458 passed in 6.56s (was 1329 in 6.50s pre-S5)
**Net new tests**: +129
**Commits**: f689f2f (F0), 9532069 (F1), 54f484d (F2), 881a288 (F3),
4f8b37b (F4), this commit (F5).

## 7-Point Bar

| # | Gate | Status | Evidence |
|---|------|--------|----------|
| 1 | Audit doc enumerates all chains + risk inventory | ✅ | `docs/audits/S5-ai-engine-chains.md` (R1–R6) |
| 2 | Behavioural tests pin the contract BEFORE any refactor | ✅ | F1–F4 commits add 129 tests; zero source changes |
| 3 | Each fix ≤500 LOC + ≥1 behavioural test | ✅ | F1: 296 LOC / 36 tests, F2: 264 LOC / 21 tests, F3: 197 LOC / 20 tests, F4: 213 LOC / 52 tests |
| 4 | Suite stays green and <15s end-to-end | ✅ | 1458 passed in 6.56s |
| 5 | ADR captures the design decision | ✅ | `docs/adrs/0007-chain-output-and-construction-contract.md` |
| 6 | Sign-off doc captures gate verdict + deferrals | ✅ | This file |
| 7 | Commits held local until P4-S10 staging gate | ✅ | All 6 S5 commits local; nothing pushed |

## What Was Pinned

### F1 — RoleProfilerChain pure helpers (36 tests)

12 helpers across the resume parsing pipeline. Each one is a silent
garbage-in-garbage-out risk:

- `_is_noise_line`: page markers, CV header, confidential, separators,
  page-no detection.
- `_clean_resume_text`: empty/None handling, bullet normalisation
  (●/•/▪/▸/►/◆/◇/■/□/★/☆/→ → `-`), whitespace collapse, mangled-URL
  repair (`linkedin . com` → `linkedin.com`), noise-line removal.
- `_normalize_date`: None and non-string-safe, 5 "present" synonyms
  canonicalised.
- `_clean_skill`: invalid level/category default to `intermediate` /
  `technical`, years bounded to `(0, 50]`, unparseable years string
  rejected.
- `_deduplicate_skills`: higher-level wins, case-insensitive,
  longer-years wins, unique preservation.
- `_compute_parse_confidence`: zero-on-empty, capped at 1.0, monotone
  reward, non-dict contact info doesn't crash.
- `_build_parse_warnings`: missing name/email/skills detected, silent
  on strong result.
- `_sort_by_date`: current-first, "Present" treated as current,
  past roles ordered year-desc.

### F2 — `_validate_result` across 7 chains (21 tests)

The defensive validator at the end of every chain's public method.
Drift here = silent crashes downstream:

- GapAnalyzer: compatibility_score clamping `[0, 100]`, 14 required
  keys backfilled, string recommendations dropped, priority sort.
- CareerConsultant: 5 required keys.
- LinkedInAdvisor: 7 required keys, default overall_score=50.
- MarketIntelligence: 6 required keys, market_overview shape,
  salary_insights shape (currency + range_low/median/high).
- SalaryCoach: 8 required keys.
- LearningChallenge: 11 required keys, defaults
  (`intermediate` / `8h`).
- RoleProfiler: 11 required keys, parse_confidence/warnings emitted,
  non-dict input safely reset.

### F3 — CompanyIntel fallback + Validator security primitives (20 tests)

Last-resort safety net + XSS bouncer:

- `CompanyIntelChain._minimal_fallback`: 8 required top-level keys,
  `confidence='low'` is a fixed contract, tech-keyword extraction
  (case-insensitive, capped at 10), unknown-word rejection,
  company name preserved.
- `ValidatorChain.validate_json_structure`: pass/fail/missing-list
  contract, None-value treated as missing.
- `ValidatorChain.sanitize_content` (SECURITY): script tag stripping,
  multiline script blocks, `on*` event handlers,
  `javascript:` URI scheme stripped, safe markdown preserved.
- `ValidatorChain.check_for_fabrication`: subset → no warnings,
  invented company flagged, case-insensitive matching,
  empty-experience safe, blank company entries skipped.

### F4 — Chain construction surface (52 tests)

20 exported LLM chains pinned to `__init__(self, ai_client)`:

- 20-chain export count locked.
- 19 standard chains pin `__init__(ai_client)` parametrically.
- 16 chains smoke-instantiate via `cls(object())`.
- DocumentPackPlanner pinned as the SOLE non-standard `__init__`
  exception (catalog dependency); allowlist drift fails the build.
- 13 chains pinned to expose at least one async public method
  (sync drift would block the asyncio executor).

### F5 — ADR-0007 + sign-off (this commit)

- `docs/adrs/0007-chain-output-and-construction-contract.md` —
  codifies `_validate_result` contract, construction surface
  allowlist, pure-helper testability rule.
- This sign-off doc.

## Deferrals (rationale)

These are tracked but intentionally NOT in S5 scope:

1. **R5 — JSON schema enforcement against `_validate_result`
   output.** 7 schemas live in `ai_engine/schemas/` but are not
   wired in. Deferred to S6 because it bundles naturally with
   prompt versioning (move embedded prompts to
   `ai_engine/prompts/`). S5's `_validate_result` contract is the
   prerequisite — schemas can now safely tighten because the
   key surface is locked.

2. **Single registry / factory.** Centralising chain construction
   would close the surface entirely (chain name → instance). Defer
   to a dedicated infrastructure squad — touches the service layer
   too broadly for an S5-bounded change.

3. **Chain method-level signature pinning beyond F4.** F4 pins
   constructors and async-method existence. Pinning the ~50 public
   method signatures across all chains would be `inspect.signature`
   ceremony. Defer unless a service-layer drift incident demonstrates
   the need; existing `test_chain_contracts.py` already pins the 4
   highest-risk methods (LearningService → `generate_daily_set`,
   SalaryCoachChain → `years_experience`, etc.).

4. **Property-based tests on `_clean_skill` / `_deduplicate_skills`.**
   Hypothesis would generate adversarial skill payloads. Worth doing
   but adds a dev dependency; defer until the chain registry lands
   (single place to wire fuzz infrastructure).

## Suite Trajectory

| Squad | Pre | Post | Δ tests | Time |
|-------|-----|------|---------|------|
| S4 close | 1314 | 1329 | +15 | 6.50s |
| S5-F0 audit | 1329 | 1329 | 0 | 6.50s (no test change) |
| S5-F1 RoleProfiler helpers | 1329 | 1365 | +36 | 7.29s |
| S5-F2 _validate_result | 1365 | 1386 | +21 | 6.22s |
| S5-F3 CompanyIntel + Validator | 1386 | 1406 | +20 | 7.24s |
| S5-F4 Construction surface | 1406 | 1458 | +52 | 6.56s |

S5 net: **+129 tests, suite stays under 8s.**

## Verdict

✅ **GREEN.** All 7 gates met. Proceed to S6.
