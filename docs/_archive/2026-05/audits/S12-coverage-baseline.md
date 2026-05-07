# S12-F3 — Coverage baseline (deferred risk follow-up)

**Date:** 2026-04-29
**Squad:** S12 (QA & Release Engineering)
**Risk addressed:** R3/R4 — coverage thresholds were proposed in the
S12 audit but deferred at sign-off because adding hard floors without
empirical baselines risks blocking innocuous PRs.

This document records the **measured baseline** so a future PR can set
thresholds 5–10 percentage points below actuals.

## Backend (Python)

Measured locally on `main` @ `45c43a5` (post v1.0.1) with:

```bash
cd backend
python -m pytest tests/ --cov=app --cov=../ai_engine --cov-report=term -q
```

| Metric         | Value             |
|----------------|-------------------|
| Tests passed   | 2004              |
| Tests skipped  | 11                |
| Statements     | 24,133            |
| Missed         | 11,188            |
| **Coverage**   | **54%**           |
| Wall time      | ~144s (local)     |

### Notable hot/cold modules

- `app/services/job_sync.py` — 98% (covered well)
- `app/services/quality_scorer.py` — 91%
- `app/services/webhook.py` — 84%
- `app/services/usage_guard.py` — 74%
- `app/services/profile.py` — 67%
- `app/services/pipeline_runtime.py` — 43% (largest module: 1,416 stmts)
- `app/services/file_parser.py` — 14%
- `app/services/global_skills.py` — 16%
- `app/services/knowledge_library.py` — 16%
- `app/services/learning.py` — 18%
- `app/services/job_watchdog.py` — 0% (untested entirely)
- `app/services/progress_calculator.py` — 0%
- `app/worker.py` — 0%

## Frontend (TypeScript / Vitest)

**Not measured.** Both Vitest coverage providers fail on this checkout:

- `@vitest/coverage-v8` — sourcemap parser cannot handle the space in
  the absolute path `/Users/balabollineni/HireStack AI/frontend/...`,
  throws `ENOENT` on every transformed file.
- `@vitest/coverage-istanbul` — runs to completion but Node V8
  aborts with OOM during istanbul report generation.

Recommendation: measure in CI (Linux runners, no path spaces, more RAM)
once the coverage provider is wired into `.github/workflows/ci.yml`.
Until then, the frontend baseline is **unmeasured** and any threshold
should be omitted (current state) or set conservatively (≥40%) once
CI produces a number.

## Mobile (Kotlin / JaCoCo)

Out of scope for S12-F3 (different toolchain; previously confirmed
suite of 45 Compose tests passes but no JaCoCo HTML report exists yet).

## Recommended next-PR thresholds (when wiring `--cov-fail-under`)

| Surface  | Measured | Floor (−5pp) | Floor (−10pp, conservative) |
|----------|----------|--------------|-----------------------------|
| Backend  | 54%      | **49%**      | 44%                         |
| Frontend | n/a      | n/a          | n/a (set after CI measures) |

Keep the gate **advisory** (`continue-on-error: true`) for the first
1–2 weeks to surface drift before promoting to required.

## Why this isn't S12-F3 itself

S12-F3 was deferred at squad sign-off (see
`docs/audits/S12-qa-release-engineering-signoff.md`). This file is the
**measurement step**; the **enforcement step** (adding `--cov-fail-under`
to `backend/pytest.ini` or CI) is a separate PR so the threshold change
is reviewable independently from the baseline data.
