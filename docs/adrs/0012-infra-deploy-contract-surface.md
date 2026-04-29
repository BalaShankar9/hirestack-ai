# ADR-0012 — Infra & Deploy Contract Surface

**Status:** Accepted
**Squad:** S10 (Infra & Deploy)
**Date:** 2026-04-21
**Supersedes:** none
**Related:** ADR-0003 (health vs readiness), ADR-0010 (frontend contract), ADR-0011 (mobile contract)

## Context

Pre-S10 audit (`docs/audits/S10-infra-deploy.md`) catalogued **17 risks** in the deploy surface. The most material were:

- **R1 (P0)** — `scripts/smoke_test.py` and one helper script carried hardcoded Supabase service-role JWTs and a real user credential.
- **R5 / R6** — Four uvicorn entrypoint declarations (`backend/Dockerfile`, `infra/Dockerfile.backend`, `Procfile`, `railway.toml`, `Makefile`) had drifted; two pointed at `app.main:app`, which **does not exist** (the FastAPI app lives at `backend/main.py`, not `backend/app/main.py`).
- **R3 / R4** — Two compose files (`docker-compose.yml`, `infra/docker-compose.yml`) with subtly different service definitions; the "prod" file shipped dev bind mounts that would mask the baked-in image during a real deploy.
- **R8** — `.github/workflows/deploy.yml` health gate was an inline `curl` loop that tested only HTTP 200 on `/health`, ignoring the richer `scripts/health_check.py` that the repo already shipped.
- **R12** — No test pinned the cross-contract between `/health` (backend) and `scripts/health_check.py` (deploy gate), so a backend refactor could silently break the gate.

## Decision

The **canonical** infra/deploy contract is:

| Concern | Canonical | Notes |
|---|---|---|
| FastAPI app object | `backend/main.py` (`app = FastAPI(...)`) | `backend/app/main.py` does **not** exist; never reintroduce that path. |
| Uvicorn entrypoint (cwd=`backend/`) | `main:app` | Used by `Procfile`, `railway.toml`, `backend/Dockerfile`, `Makefile dev-backend`. |
| Uvicorn entrypoint (cwd=repo root) | `backend.main:app` | Used by `infra/Dockerfile.backend`. |
| `PYTHONPATH` for Procfile / Railway | `/app` | Pinned in both. |
| Compose file | `infra/docker-compose.yml` | Root `docker-compose.yml` deleted. No bind mounts on backend/frontend/worker. Named volume `uploads:/app/uploads` retained. |
| Deploy health gate | `python scripts/health_check.py --backend ... --frontend ...` | Wrapped in 6×30s retry; exit 2 (DEGRADED) → retry-then-fail; exit 1 (CRIT) → fail immediately. |
| Local dev backend | `make dev-backend` | Documented inline in compose where bind mounts used to live. |
| Secrets in source | None | CI scanner (regex JWT/AWS/GH-PAT/OpenAI) gates every PR; allow-list in `backend/tests/test_no_hardcoded_secrets.py`. |
| `/health` response contract | 200 (or 503 = DEGRADED) + JSON + `"status"` ∈ `{"healthy","degraded"}` | Pinned by `backend/tests/test_health_contract.py`. |
| `/openapi.json` response contract | 200 + body contains `"openapi"` | Pinned by `backend/tests/test_health_contract.py`. |

## Consequences

### Positive
- Two long-broken uvicorn entrypoints are corrected; both resolve to the same FastAPI instance (asserted by `test_canonical_app_object_is_unique`).
- Compose drift is removed by deletion; only the `infra/` file is authoritative.
- Deploy gate now fails closed on degraded JSON shape, missing keys, or bad latency — not just non-200.
- `/health` cannot drift its contract without breaking a unit test.
- Secret-scan is fail-closed in CI and exhaustively allow-listed (audit doc, mobile public anon key, the test file itself).

### Negative
- Two import paths (`main:app` and `backend.main:app`) co-exist. They reach the same source file but resolve to **different** sys.modules entries. The contract test asserts they are identical-by-source even when they are distinct-by-instance.
- Mobile public Supabase anon key in `mobile/android/app/build.gradle.kts` is allow-listed pending a follow-up to move it to `local.properties` (tracked under R-mobile-1, deferred to mobile-release squad).

### Deferred / Accepted Risk (from the 17-risk register)
- **R2** — `scripts/run_migrations.py` hardcodes a production Supabase reference. Tooling-only, ops-gated, accepted.
- **R7** — Smoke test scope is functional, not load. Accepted; load is k6 territory (S11).
- **R9** — `pip-audit` / `npm audit` are non-blocking informational steps. Accepted; tightening is an S12 concern.
- **R10** — GH Actions are pinned by tag, not commit SHA. Accepted; tightening is an S12 concern.
- **R11** — Container base images use `python:3.11-slim` / `node:20-alpine` by tag, not digest. Accepted; tightening is an S12 concern.
- **R13–R17** — Logging redaction, Sentry env scoping, Railway region pin, Netlify preview-build leakage, frontend env-injection audit. All forwarded to S11 (Observability & SRE).

## Verification

S10 shipped **39 new behavioural tests** across 5 fix-waves:

| Wave | Commit | Tests | Subject |
|---|---|---|---|
| F0 | `53da079` | 0 | 17-risk audit (`docs/audits/S10-infra-deploy.md`) |
| F1 | `aff6226` | 6 | Secret excise + repo-wide regex scanner |
| F2 | `008dee2` | 9 | Uvicorn entrypoint canonicalisation |
| F3 | `4aa068f` | 8 | Compose canonicalisation (root file deleted, bind mounts removed) |
| F4 | `fb70cdc` | 14 | Deploy gate uses `scripts/health_check.py` + 14 unit tests |
| F5 | `f29674e` | 2 | `/health` + `/openapi.json` cross-contract pin |

Backend suite: **1924 passed, 11 skipped** (pre-S10: 1892 passed; +32 net = +37 new − 5 prior tests obsoleted by F1–F3 cleanups). Frontend (335) and mobile (45) suites untouched.
