# S5 Audit — AI Engine Chains

**Date**: 2026-04-29
**Squad**: AI Engine Chains
**Surface**: `ai_engine/chains/` — 22 chain modules, ~7,174 LOC

## Risk inventory

### R1. Validator drift (5 chains, identical-named helpers)
Five chains carry a private `_validate_result(result: dict) -> dict`
that is the LAST line of defence between unreliable LLM output and
persisted user data:

- `role_profiler.py:RoleProfilerChain._validate_result`
- `gap_analyzer.py:GapAnalyzerChain._validate_result`
- `career_consultant.py:CareerConsultantChain._validate_result`
- `linkedin_advisor.py:LinkedInAdvisorChain._validate_result`
- `market_intelligence.py:MarketIntelligenceChain._validate_result`

These are pure functions but have ZERO unit coverage. A regression
that lets an empty / partially-failed LLM response through would
write garbage to the database silently.

### R2. RoleProfiler resume-cleaning helper bog (lines 1-647)
`RoleProfilerChain` carries 12+ pure helpers that govern resume parsing:
`_clean_resume_text`, `_is_noise_line`, `_normalize_date`,
`_clean_skill`, `_deduplicate_skills`, `_clean_experience`,
`_clean_education`, `_clean_certification`, `_clean_project`,
`_clean_contact_info`, `_sort_by_date`, `_compute_parse_confidence`,
`_build_parse_warnings`, `_enrich_skills_from_experience`. Each one
is a silent garbage-in-garbage-out risk. Any single helper drifting
silently degrades EVERY parsed resume.

### R3. Service ↔ chain kwarg drift
`backend/tests/unit/test_chain_contracts.py` already pins six chain
signatures (learning, salary, interview, ats). The other 16 chain
public methods have NO signature contract. A service caller passing
`experience_years=` to a chain that expects `years_experience=`
silently drops the value (the bug F2 of the existing chain_contracts
file fixed in salary_coach). No test prevents the same bug class
recurring elsewhere.

### R4. CompanyIntel fallback and ValidatorChain primitives
`CompanyIntelChain._minimal_fallback` is the safety net when the AI
call fails — it must always return a non-empty dict with the
contract-required keys, otherwise the rest of the pipeline dies.
`ValidatorChain.validate_json_structure`, `.sanitize_content`,
`.check_for_fabrication` are pure helpers that have no coverage but
are called from the document-generation hot path.

### R5. Schema files exist but are not enforced
`ai_engine/schemas/` carries seven JSON schemas
(`profile_schema.json`, `cv_schema.json`, `cover_letter_schema.json`,
`benchmark_schema.json`, `gap_analysis_schema.json`,
`interview_schema.json`, `ats_scan_schema.json`) — none of them
are imported by any chain or test. They're documentation, not a
contract. The closest thing to schema enforcement is the
per-chain `_validate_result` (R1).

### R6. Construction-API drift
Every chain follows the convention `__init__(self, ai_client)` plus
at least one async public method. There is no test asserting any
chain matches this convention. A future contributor refactoring a
chain to `__init__(client, prompt_dir)` would silently break the
DI container in `backend/app/services/`.

## Fix queue (≤6 fixes per squad rule)

| ID  | Title                                                                                          | LOC budget |
|-----|------------------------------------------------------------------------------------------------|-----------:|
| F0  | This audit                                                                                     |  ~150      |
| F1  | RoleProfilerChain pure-helper invariants — noise filter, date norm, skill dedup, confidence    |  ~400      |
| F2  | `_validate_result` contract pinned across the 5 chains that share the helper                   |  ~400      |
| F3  | CompanyIntelChain._minimal_fallback + ValidatorChain primitives                                |  ~250      |
| F4  | Chain construction surface — every public chain accepts `(ai_client)`, exposes expected methods|  ~300      |
| F5  | ADR-0007 (chain output validation contract) + S5 sign-off                                      |  ~200      |

## Out of scope (deferred)

- **Schema enforcement loop**: making `_validate_result` validate
  against the matching JSON schema in `ai_engine/schemas/` is a
  larger refactor (involves picking a schema library, wiring per-chain
  schema lookup, and deciding the soft-vs-hard failure policy).
  Will land in a dedicated S6+ pass once the contract is pinned.
- **Prompt version control**: no prompts live in `ai_engine/prompts/`
  today (only `__init__.py`); they're embedded in chain source.
  Refactoring prompts into versioned templates is a S6+ swing.
- **Quality measurement**: `OutputScorer` is the building block but
  there's no scheduled scoring loop. Out of scope for this squad.

## Verification gate

Every PR keeps `cd backend && pytest tests/unit -q` green and <15s.
Baseline at S5 start: **1329 passed in 6.50s**.
