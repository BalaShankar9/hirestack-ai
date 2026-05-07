# S10 — Infra & Deploy — Sign-Off

**Date:** 2026-04-21
**Squad lead:** GitHub Copilot (autonomous)
**Status:** ✅ Complete — staging gate cleared

## Scope

Close the 17 risks identified in `docs/audits/S10-infra-deploy.md`. Apply 5 surgical fix-waves; finalise contract in ADR-0012.

## Outcome

| Metric | Pre-S10 | Post-S10 | Δ |
|---|---|---|---|
| Backend tests | 1892 | 1924 | +32 |
| Backend skipped | 11 | 11 | 0 |
| Backend duration | 120.22s | 118.73s | -1.49s |
| Frontend tests | 335 | 335 | 0 |
| Mobile tests | 45 | 45 | 0 |
| P0 risks open | 1 (R1 hardcoded JWTs) | 0 | -1 |
| Drift in entrypoint declarations | 4 paths, 2 broken | 1 canonical mapping | resolved |
| Compose files | 2 (drifted) | 1 (`infra/`) | resolved |
| Deploy gate richness | curl 200 only | `scripts/health_check.py` w/ JSON + key checks | resolved |

## Fix-Wave Ledger

1. **F0 `53da079`** — `docs/audits/S10-infra-deploy.md` (17-risk register).
2. **F1 `aff6226`** — `scripts/smoke_test.py` + `scripts/test_module8_remaining_backend.py` env-driven; CI secret-scanner regex tightened; `backend/tests/test_no_hardcoded_secrets.py` (6 tests). **Note**: leaked service-role JWT for project `dkfmcnfhvbqwsgpkgoag` remains in git history pre-`aff6226`; user is rotating in Supabase dashboard out-of-band.
3. **F2 `008dee2`** — `app.main:app` (broken — that module does not exist) replaced with `main:app` in `backend/Dockerfile` and `Makefile`; `backend/tests/test_entrypoint_consistency.py` (9 tests).
4. **F3 `4aa068f`** — Root `docker-compose.yml` deleted; `infra/docker-compose.yml` stripped of dev bind mounts; `backend/tests/test_compose_canonicalisation.py` (8 tests).
5. **F4 `fb70cdc`** — `.github/workflows/deploy.yml` health gate now invokes `scripts/health_check.py`; `backend/tests/test_health_check_script.py` (14 tests).
6. **F5 `f29674e`** — `backend/tests/test_health_contract.py` (2 tests) pins `/health` + `/openapi.json` against the deploy gate; small F2/F3 interaction patched.

## Carried-Forward Risks

Documented in ADR-0012 §"Deferred / Accepted Risk":
- R2, R7, R9, R10, R11 — accepted as-is (S12 tightening candidates).
- R13–R17 — forwarded to S11 (Observability & SRE).
- R-mobile-1 — Supabase public anon key in `build.gradle.kts` allow-listed; mobile-release squad to move to `local.properties`.

## Out-of-Band Action

- **User**: rotate the Supabase service-role key for project `dkfmcnfhvbqwsgpkgoag` (the JWT remains in git history before commit `aff6226`).

## Gate Decision

**PROCEED to S11** (Observability & SRE).
