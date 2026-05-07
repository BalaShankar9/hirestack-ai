# S12 — QA & Release Engineering — Sign-Off

**Date:** 2026-04-21
**Squad lead:** GitHub Copilot (autonomous)
**Status:** ✅ Complete (final squad of the 12-squad blueprint)

## Scope

Close the 10 risks in `docs/audits/S12-qa-release-engineering.md`. P1
risks were R1 (no `CHANGELOG.md`) and R2 (`settings.app_version`
hardcoded, defeating S11-F2's Sentry release-bisect intent). The most
urgent P2 was R5 (pytest deadlock guard silently disabled).

## Outcome

| Metric | Pre-S12 | Post-S12 | Δ |
|---|---|---|---|
| Backend tests | 1981 | 2000 | +19 |
| Backend skipped | 11 | 11 | 0 |
| Backend duration | 112.74s | 115.15s | +2.41s |
| Frontend tests | 335 | 335 | 0 |
| Mobile tests | 45 | 45 | 0 |
| `Unknown config option: timeout` warning in CI | yes | no | fixed |
| P1 risks open | 2 | 0 | -2 |
| P2 risks open | 4 | 2 (deferred R3/R4) | -2 |

## Fix-Wave Ledger

1. **F0 `8bc3f2f`** — `docs/audits/S12-qa-release-engineering.md`
   (10-risk register).
2. **F1 (next sha)** — `CHANGELOG.md` (Keep a Changelog 1.1.0); 7
   contract tests pin file existence, header, `[Unreleased]` section,
   ≥1 versioned release, and S10/S11/S12 mentions.
3. **F2 (next sha)** — `backend/VERSION` as single source of truth;
   `config._read_version()` reads it at import time; 9 tests pin file
   existence, semver shape, single-line constraint, Settings drift
   guard, source-inspection (no literal), and parametric edge inputs.
4. **F3** — **Deferred** (coverage thresholds need empirical baseline).
5. **F4 (next sha)** — `pytest-timeout>=2.3,<3.0` in
   `backend/requirements.txt`; 3 tests pin requirement, `pytest.ini`
   directive, plugin importability. Closes the
   `Unknown config option: timeout` warning.
6. **F5 (this commit)** — `RELEASE.md` runbook + ADR-0014 + this
   sign-off.

## Carried-Forward Risks

- R3/R4 (coverage thresholds, frontend + backend) — deferred; needs
  baseline measurement first.
- R6 (automated rollback) — Railway operations.
- R7 (SHA-pin GH Actions) — operations.
- R8 (promote deps-audit to required) — needs patch-SLA process.
- R9 (auto-tag on deploy) — manual per `RELEASE.md`; future
  automation candidate.

## Out-of-Band Action

- **Operators promoting a release: bump `backend/VERSION`, move the
  `[Unreleased]` block in `CHANGELOG.md` to a versioned header, then
  push.** See `RELEASE.md`.

## Gate Decision

**12-squad blueprint COMPLETE.** All squads S1–S12 have signed off.
Recommend the user be offered: (a) a final cross-squad health check
(re-run all 3 suites + eval gate), (b) authorisation to push the
local commits to `origin/main`, (c) drafting the next development
roadmap.
