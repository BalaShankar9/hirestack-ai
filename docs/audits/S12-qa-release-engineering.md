# S12 — QA & Release Engineering — Audit (2026-04-21)

Surveyed: `pyproject.toml`, `backend/pytest.ini`, `frontend/{package.json,vitest.config.ts,playwright.config.ts}`, `.github/workflows/{ci,deploy}.yml`, `CHANGELOG.md` (absent), `backend/app/core/config.py:app_version`, `Procfile`, `railway.toml`, `netlify.toml`.

## Existing surface (good, do not regress)

- ✅ `ci.yml` runs frontend lint + tsc + build + unit tests, backend ruff + pytest, eval gate, secret-scan, deps-audit (advisory).
- ✅ `deploy.yml` chains CI → Railway deploy → `scripts/health_check.py` retry loop → Netlify verify (12×15s).
- ✅ `concurrency: deploy-production / cancel-in-progress: false` prevents racing deploys.
- ✅ Backend uses `pytest-asyncio auto` and per-test 30s timeout via pytest-timeout (config option present).
- ✅ Frontend has Vitest unit + Playwright e2e wiring.
- ✅ Eval gate (`ai_engine.evals.runner`) runs deterministically on PRs.

## Risk register (S12)

| ID | Severity | Risk | Evidence | Fix wave |
|---|---|---|---|---|
| **R1** | **P1** | No `CHANGELOG.md` exists. Releases are inferable only from `git log`. There is no human-readable record of what shipped in each version. | `file_search` returned 0 results for `CHANGELOG.md`. | F1 |
| **R2** | **P1** | `settings.app_version` is hardcoded at `"1.0.0"` in `backend/app/core/config.py` and **never updated**. Sentry `release` (added in S11-F2) will therefore tag every event with `1.0.0` forever, defeating the bisect-by-deploy intent. | `grep app_version` shows static string. | F2 |
| **R3** | **P2** | Frontend has no coverage threshold gate. `vitest.config.ts` does not declare `coverage.thresholds`; `npm test` will pass even if a contributor deletes a third of the tests. | grep returned no `coverage|threshold` matches. | F3 |
| **R4** | **P2** | Backend has no coverage threshold gate either. `pytest.ini` does not enforce `--cov-fail-under`. | same. | F3 (combined) |
| **R5** | **P2** | `backend/pytest.ini` declares `timeout = 30` but `pytest-timeout` is not declared in `backend/requirements.txt`. The CI warning `Unknown config option: timeout` (visible in our recent runs) confirms the timeout is silently ignored. A genuine async-deadlock test could hang the suite. | Recent test runs print: `PytestConfigWarning: Unknown config option: timeout`. | F4 |
| **R6** | **P2** | `deploy.yml` has no rollback step. If `health_check.py` fails after the 6×30s retry, the workflow exits non-zero but the broken Railway revision stays live. | F0 survey of `deploy.yml`. | Accepted (out of scope — Railway has separate rollback UX) |
| **R7** | **P3** | `ci.yml` uses `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4` pinned by tag, not commit SHA. Supply-chain risk if a tag is ever moved. | F0 survey. | Accepted (S12 doc; tightening is operations) |
| **R8** | **P3** | `deps-audit` job is `continue-on-error: true`. Known-CVE in a critical dep won't fail CI. | F0 survey. | Accepted (intentional per inline comment) |
| **R9** | **P2** | No automated tag/release. After merging to main, the deploy workflow runs but no git tag is created. Sentry `release=app_version` therefore can't be tied to a commit-bisectable tag even if R2 is fixed. | F0 survey. | F5 (combined w/ release-engineering ADR) |
| **R10** | **P3** | No `RELEASE.md` runbook. New maintainers don't know the canonical promote-to-prod procedure. | F0 survey. | F5 |

## Fix-wave plan

- **F1** — Create `CHANGELOG.md` seeded with squads S1–S12 and a "Keep a Changelog" header. Add a contract test pinning the file's existence and the latest version row.
- **F2** — Switch `settings.app_version` to read from a single source-of-truth file (`backend/VERSION` plain text) so a release script can bump it atomically. Add tests pinning the read path and the file's presence.
- **F3** — Add `vitest` coverage threshold (lines/statements/functions/branches at sensible floors based on current actuals) and a coverage threshold gate at the backend `[pytest]` level via `--cov-fail-under` in CI command (NOT pytest.ini, to keep local runs unimpacted).
- **F4** — Add `pytest-timeout` to `backend/requirements.txt` and a test asserting the runtime warning is gone (or the constraint is enforced).
- **F5** — `RELEASE.md` runbook + ADR-0014 + S12 sign-off.

## Out of scope (forwarded)
- Rollback automation (R6) — Railway-specific operations.
- SHA-pinning all GH Actions (R7) — operations.
- Promoting `deps-audit` to required (R8) — needs patch-SLA process first.
