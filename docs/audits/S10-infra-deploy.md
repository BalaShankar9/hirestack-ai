# S10 — Infra & Deploy Audit (F0)

**Date**: 2026-04-21  
**Scope**: `docker-compose.yml`, `infra/docker-compose.yml`, `infra/Dockerfile.{backend,frontend}`, `backend/Dockerfile`, `frontend/Dockerfile`, `Procfile`, `railway.toml`, `netlify.toml`, `.github/workflows/{ci,deploy}.yml`, `.dockerignore` (root + per-service), `Makefile`, `scripts/{health_check,smoke_test,run_migrations}.py`.

## Risk Register

| # | Severity | File | Risk |
|---|---|---|---|
| **R1** | **P0 / CRITICAL** | `scripts/smoke_test.py:5-6` | **Hardcoded production Supabase JWTs committed to repo** — both `ANON_KEY` and `SERVICE_ROLE_KEY` for `dkfmcnfhvbqwsgpkgoag.supabase.co` are inline string literals. The CI secret-scan regex (`ci.yml` "Scan for hardcoded secrets") only matches `sk-proj-`, `AKIA`, `ghp_`, `ghu_` patterns and **does not catch Supabase JWTs**. **Service-role grants full bypass of RLS.** Must (a) excise from source, (b) require env vars, (c) extend the scanner regex to include `eyJ[A-Za-z0-9._-]{40,}` JWT shapes. |
| R2 | HIGH | `scripts/run_migrations.py:30` | Production Supabase project ref `cigdytublaotsiyjlsze` hardcoded as default fallback for migration target. A casual `python scripts/run_migrations.py` from a misconfigured shell can target prod if `SUPABASE_DB_PASSWORD` env happens to be set. Should require explicit `--project-ref` or fully fail-closed when `DATABASE_URL` absent. |
| R3 | HIGH | `docker-compose.yml` (root) vs `infra/docker-compose.yml` | **Two divergent compose files.** Root: no `worker` service, no Redis password, mounts no source volumes (immutable image), `REDIS_URL=redis://redis:6379` (no auth). Infra: includes `worker`, `redis-server --requirepass`, bind-mounts `../backend:/app` (overrides image, defeats prod parity). Risk of "works in one, breaks in the other" + ambiguity about which is canonical. Need ADR designating one as authoritative + a contract test that the surviving compose file `docker compose config -q` parses cleanly. |
| R4 | HIGH | `infra/docker-compose.yml:18, :44` | Bind mounts `../backend:/app` and `../frontend:/app` shadow the multi-stage build output (overlay erases `dist`/`.next/standalone`). This is dev-mode wiring living in the file labelled "production". Either split into `compose.dev.yml` overlay or remove the volumes from the canonical file. |
| R5 | HIGH | `backend/Dockerfile` vs `infra/Dockerfile.backend` | Two Dockerfiles for the same service. Diverge on (a) `COPY . .` (root) vs `COPY backend/ ./backend/ && COPY ai_engine/ ./ai_engine/` (infra) → root variant ships entire repo into the image; (b) entrypoint module path: `uvicorn app.main:app` (root) vs `uvicorn backend.main:app` (infra) — at most one matches the actual import surface. Same drift exists for frontend. **Procfile/railway.toml use a third path** (`cd /app/backend && python -m uvicorn main:app`). |
| R6 | HIGH | `Procfile`, `railway.toml`, `infra/Dockerfile.backend`, `backend/Dockerfile` | **Four different uvicorn entrypoints in production config**: `main:app`, `app.main:app`, `backend.main:app`, plus the actual repo top-level `backend/main.py` (per workspace tree). At most one is correct; the others are landmines for whichever platform deploy gets selected. Need a single canonical entrypoint constant. |
| R7 | MEDIUM | `scripts/smoke_test.py` | Whole module is hardcoded against `127.0.0.1:8000` and a single test email; it's a one-shot script, not a deployable smoke suite. Cannot be invoked from CI against staging/prod safely. (Plus R1.) |
| R8 | MEDIUM | `.github/workflows/deploy.yml:32-35` | Deploys backend on every push to `main` **without running `scripts/health_check.py` against the deployed URL** — only an inline ad-hoc `curl /health` loop. The repo has a richer health checker (`scripts/health_check.py`) with critical/non-critical contract; deploy workflow ignores it. |
| R9 | MEDIUM | `.github/workflows/ci.yml:122-152` | `deps-audit` job uses `continue-on-error: true` AND `pip-audit ... \|\| true` AND `npm audit ... \|\| true` — triple-nested ignoring of vuln signal. The comment acknowledges this is intentional; once a baseline exists it must be promoted to required, but no follow-up issue is tracked in the repo. |
| R10 | MEDIUM | `.github/workflows/ci.yml` | No `actions/setup-*` SHA pinning — uses floating `@v4` / `@v5` tags. Supply-chain surface for tag-replay attacks. |
| R11 | MEDIUM | `infra/docker-compose.yml`, root `docker-compose.yml` | None of the base images are pinned by digest (`redis:7-alpine`, `python:3.11-slim`, `node:20-alpine`). At least `infra/Dockerfile.backend` pins minor (`python:3.11.9-slim`) but root `backend/Dockerfile` only pins `python:3.11-slim`. Reproducibility gap. |
| R12 | MEDIUM | `backend/Dockerfile`, `infra/Dockerfile.backend` | `HEALTHCHECK` uses `curl http://localhost:8000/health` but `/health` path is asserted by `scripts/health_check.py` to also accept `/openapi.json` and return `{"status": ...}` JSON — there is no test pinning what `/health` actually returns from a built image. |
| R13 | LOW | `frontend/Dockerfile`, `infra/Dockerfile.frontend` | Healthcheck spiders `http://localhost:3000` (root path). Next.js standalone server returns 200 here, but if the homepage SSR path ever throws this also flips DEGRADED → DOWN. A dedicated `/api/health` route would be more honest. |
| R14 | LOW | `infra/Dockerfile.frontend:5` | `RUN npm ci --only=production` in the `deps` stage is unused — the `builder` stage immediately re-runs `npm ci` for full install. Wasted cache layer (~80MB). |
| R15 | LOW | `netlify.toml` | Hardcodes `NEXT_PUBLIC_API_URL = "https://hirestack-ai-production.up.railway.app"` as build-environment fallback. Couples frontend deploy to railway URL by string. Should at minimum be referenced from one source of truth. |
| R16 | LOW | Root `.dockerignore` | Excludes `*.md` globally — but `frontend/public/*` may include README assets etc. Low impact today but a footgun. |
| R17 | LOW | `Makefile` | `dev-backend` runs `uvicorn app.main:app` while `Procfile` / `railway.toml` use `main:app` and `infra/Dockerfile.backend` uses `backend.main:app`. Same R5/R6 drift surfaces in the developer command path. |

## Behavioural-Test Plan (S10-F1..Fn)

Each fix gets ≥1 test pinning the fixed contract.

- **F1 — R1 (P0)**: Excise hardcoded JWTs from `scripts/smoke_test.py`, require env vars, extend CI secret scanner. Test = pytest that scans the repo for `eyJ[A-Za-z0-9._-]{40,}` outside `*.example` and asserts none found, plus a unit test that `smoke_test.py` exits non-zero with a clear message when env vars missing.
- **F2 — R5/R6/R17**: Pick one canonical backend entrypoint. Test = `tests/test_entrypoint_consistency.py` parses `Procfile`, `railway.toml`, both `Dockerfile`s, `Makefile`, and `infra/docker-compose.yml`, asserts they all reference the same `module:attr`, and asserts the import actually resolves (`importlib.import_module(...)`).
- **F3 — R3/R4**: ADR designating one canonical compose file, remove dev volumes from the production file (or move to overlay). Test = subprocess `docker compose -f <canonical> config -q` (parse-only — no daemon needed) + assert no bind-mount keys under production services.
- **F4 — R8**: Wire `scripts/health_check.py` into `deploy.yml`. Test = pure-Python unit tests for `_check()` exit-code branches (already absent — need them) covering CRIT/WARN/PASS classifications.
- **F5 — R12**: Pin `/health` response contract with a backend unit test (likely already exists — verify and reference).
- (R2/R7/R9/R10/R11/R13/R14/R15/R16 deferred or rolled into F1-F5 where overlap exists; will surface in sign-off.)

## Out of Scope for S10
- Production secret rotation (org responsibility — flagged in F1).
- Migrating off Railway/Netlify or introducing Terraform.
- Building staging environment (S11/SRE).
