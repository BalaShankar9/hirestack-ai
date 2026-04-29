# ADR-0014 — QA & Release-Engineering Contract Surface

**Status:** Accepted
**Squad:** S12 (QA & Release Engineering)
**Date:** 2026-04-21
**Supersedes:** none
**Related:** ADR-0012 (infra & deploy), ADR-0013 (observability & SRE)

## Context

S10 hardened deploy mechanics. S11 hardened observability. S12 closes
the QA & release-engineering surface so a future maintainer can promote
`main` to production deterministically without consulting tribal
knowledge.

The S12 audit (`docs/audits/S12-qa-release-engineering.md`) surfaced 10
risks. The two P1s were:

- **R1**: no `CHANGELOG.md` — release content was inferable only from
  `git log`.
- **R2**: `settings.app_version` was a hardcoded `"1.0.0"`. The Sentry
  `release` pin added in S11-F2 was therefore tagging every event with
  `1.0.0`, defeating the bisect-by-deploy intent.

The most urgent P2 was R5: `pytest.ini` declared `timeout = 30` but
`pytest-timeout` was absent from `backend/requirements.txt`, so the
deadlock guard was silently disabled (verified by the
`PytestConfigWarning: Unknown config option: timeout` line that
appeared in every CI run).

## Decision

The QA / release-engineering contract surface is:

| Concern | Canonical | Pinned by |
|---|---|---|
| Release record | `CHANGELOG.md` (Keep a Changelog 1.1.0 + SemVer) | `tests/test_changelog_contract.py` |
| Version source of truth | `backend/VERSION` (single line, semver) read at import time by `backend.app.core.config._read_version` | `tests/test_version_source_of_truth.py` |
| Sentry `release` tag | `settings.app_version` (which reads `backend/VERSION`) | `tests/test_observability_redaction.py` (S11-F2) + `test_version_source_of_truth.py` |
| `/health` JSON `version` | same | existing health-shape tests |
| pytest deadlock guard | `pytest-timeout>=2.3,<3.0` declared in `backend/requirements.txt`; `timeout = 30` in `backend/pytest.ini` | `tests/test_pytest_timeout_dependency.py` |
| Release procedure | `RELEASE.md` (canonical runbook) | hand-maintained, referenced from ADR |
| Coverage thresholds | **Deferred** — see Consequences below | n/a |

## Consequences

### Positive
- Bumping a single file (`backend/VERSION`) atomically updates Sentry
  releases, `/health` JSON, and any downstream version emitter. The
  Sentry release-bisect intent of S11-F2 is now actually delivered.
- Contributors can read `CHANGELOG.md` instead of `git log` to know
  what changed in each release. Contract tests prevent silent removal
  of the file or its required sections.
- `pytest-timeout` is now a real dependency and `pytest.ini`'s
  `timeout = 30` actually enforces. Async deadlocks fail the test
  rather than hanging CI.
- `RELEASE.md` makes the deploy procedure self-service. No more
  "ask the platform team how to promote".

### Negative
- Bumping a release now requires editing two files (`backend/VERSION`
  and `CHANGELOG.md`) plus tagging post-deploy. Documented in
  `RELEASE.md`. Acceptable: this is the same as every well-run
  release pipeline.
- `backend/VERSION` adds a new file that release scripts must touch.
  We have no release script today; the runbook is hand-driven.

### Deferred / Accepted Risk
- **R3/R4** (no coverage thresholds, frontend + backend) — deferred.
  Adding arbitrary floors risks blocking innocuous PRs. Recommended
  follow-up: measure current coverage, then PR floors 5–10pp below
  actuals.
- **R6** (no automated rollback on health-check failure) — Railway
  operations concern. Documented in `RELEASE.md`.
- **R7** (GitHub Actions tag-pinned, not SHA-pinned) — operations.
- **R8** (`deps-audit` advisory only) — intentional per inline
  comment in `ci.yml`. Promote once we have a patch-SLA.
- **R9** (no automated git-tag on deploy) — `RELEASE.md` documents
  the manual tag step. Could be automated via a `release` workflow
  triggered on `backend/VERSION` change in a future iteration.

## Verification

S12 shipped **19 new behavioural tests** across 4 fix-waves (F3
deferred):

| Wave | Commit | Tests | Subject |
|---|---|---|---|
| F0 | `8bc3f2f` | 0 | 10-risk audit |
| F1 | (next) | 7 | `CHANGELOG.md` + Keep a Changelog header pin |
| F2 | (next) | 9 | `backend/VERSION` source of truth + `_read_version` + Settings drift guard |
| F3 | — | 0 | **Deferred** (coverage thresholds need baseline measurement) |
| F4 | (next) | 3 | `pytest-timeout` declared + `pytest.ini` timeout retained + plugin importable |
| F5 | (this commit) | 0 | `RELEASE.md` + ADR-0014 + S12 sign-off |

Backend suite: **2000 passed, 11 skipped** (post-S11: 1981 → +19).
Frontend (335) + mobile (45) untouched.
