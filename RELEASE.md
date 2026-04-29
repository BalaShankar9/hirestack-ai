# Release Runbook

The canonical procedure for promoting `main` to production. Maintained
by the platform team; ratified in ADR-0014.

## TL;DR

1. Bump `backend/VERSION` (single source of truth).
2. Move the `[Unreleased]` block in `CHANGELOG.md` under a new
   `## [x.y.z] — YYYY-MM-DD` header.
3. Open a PR titled `release: vX.Y.Z`. Wait for green CI.
4. Merge to `main`. The `Deploy` workflow runs automatically:
   - Backend → Railway (`hirestack-ai` service)
   - Frontend → Netlify (auto-deploy + verify)
5. Tag the merge commit `vX.Y.Z` and push the tag.

## Single source of truth

| Surface | Source |
|---|---|
| Sentry `release` tag | `settings.app_version` ← `backend/VERSION` |
| `/health` JSON `version` field | same |
| `X-App-Version` header (if set) | same |
| `CHANGELOG.md` `[x.y.z]` section header | hand-edited per release |
| Git tag `vX.Y.Z` | hand-tagged after deploy verifies green |

Bump `backend/VERSION` and everything downstream follows on next deploy.
The contract tests in `backend/tests/test_version_source_of_truth.py`
prevent reintroducing a hardcoded literal.

## Pre-deploy checklist

- [ ] `backend/VERSION` bumped (semver per the change kind:
      patch=bugfix, minor=feature, major=breaking).
- [ ] `CHANGELOG.md` `[Unreleased]` moved to new versioned block.
- [ ] `[Unreleased]` block re-seeded with empty subsections.
- [ ] CI green on the release PR (frontend + backend + eval gate +
      security + deps-audit advisory).
- [ ] No `.env` accidentally tracked (CI guard).
- [ ] No new hardcoded secrets (CI guard).
- [ ] `METRICS_AUTH_TOKEN` already set in production env (S11-F1
      requirement; not required for the deploy itself but required
      for `/metrics` to be reachable).

## Deploy

The `Deploy` workflow (`.github/workflows/deploy.yml`) triggers on
every push to `main`.

It does the following, gated on `concurrency: deploy-production /
cancel-in-progress: false` so two simultaneous deploys cannot race:

1. Re-runs `ci.yml` as a `workflow_call`. If anything fails the
   deploy aborts before any infrastructure is touched.
2. Backend → Railway via `railway up --service hirestack-ai --detach`.
3. Backend health check via `scripts/health_check.py` (6 retries
   × 30s) hitting both backend and frontend domains.
4. Frontend → Netlify auto-deploys on the same merge; the workflow
   polls `https://hirestack.tech/` (12 × 15s) until 200.

If health-check fails after 6×30s the workflow exits non-zero. The
broken Railway revision stays live; promote a rollback via Railway's
"Redeploy previous" UX (we don't have automated rollback in CI today —
acceptably scoped out, see ADR-0014 §Consequences).

## Post-deploy

```bash
# Sanity-check Sentry sees the new release tag.
curl -fsS https://hirestack.tech/api/health | jq .version  # => "X.Y.Z"

# Tag the deploy.
git tag -a "vX.Y.Z" -m "release: X.Y.Z"
git push origin "vX.Y.Z"
```

## Hotfix path

For urgent patches (P0 incident, security CVE):

1. Branch from `main`, fix, PR to `main`.
2. Bump `backend/VERSION` patch digit. Add CHANGELOG entry under
   `## [x.y.(z+1)] — YYYY-MM-DD` directly (skip Unreleased dance).
3. Merge → automatic deploy. Same gate, same retries.

For database hotfixes always include the migration in
`supabase/migrations/` and verify with `scripts/run_migrations.py` in
staging first.

## Verification gates (every release)

- Backend: `cd backend && python -m pytest tests/ -q` (≥2000 tests
  as of S12; no regressions, no new skips).
- Frontend: `cd frontend && npm test` (≥335 tests).
- Mobile: `cd mobile/android && ./gradlew test` (≥45 tests).
- Eval gate: `python -m ai_engine.evals.runner` (run by CI).

## Carried-forward operations work (out of scope for this repo)

- Automated rollback on health-check failure.
- SHA-pinning all GitHub Actions (currently tag-pinned).
- Promoting `deps-audit` from advisory to required (needs patch-SLA
  process first).
- Coverage threshold floors in CI (deferred from S12-F3; needs
  baseline measurement first).
- Grafana / Alertmanager provisioning from the SLO YAML manifest
  in `docs/SLO.md`.
