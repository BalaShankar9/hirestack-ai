---
title: DevOps & Infrastructure Context
last_synced: 2026-05-08
watch_paths:
  - infra
  - .github/workflows
  - Procfile
  - railway.toml
  - netlify.toml
  - backend/Dockerfile
  - frontend/Dockerfile
  - infra/Dockerfile.backend
  - infra/Dockerfile.frontend
  - Makefile
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#9-platform-and-deployment
  - docs/runbooks/
update_when:
  - a new deploy target is added (new Railway service, new Netlify env)
  - the staging-mirror compose changes
  - a CI gate is added or made required
  - the Temporal namespace or task queue layout changes
  - the Redis topology changes (new cluster, new shard)
---

# DevOps & Infrastructure Context

> The runtime behind the brain. Boring on purpose (Principle P4): managed
> services, opinionated images, immutable deploys. Innovation budget goes
> to AI runtime, not infra plumbing.

---

## TL;DR — 12 lines

1. **Two clouds:** Netlify (frontend) and Railway (all backend processes).
   No Kubernetes today; revisit at Stage B (>10k DAU or >100 RPS sustained).
2. **Backend has 4 deployables**, one Procfile entry each: `api`,
   `worker`, `scheduler`, `temporal_worker`. They share a single image.
3. **Database:** Supabase Postgres (managed). 61 migrations under
   `supabase/migrations/`.
4. **Queue:** Redis Streams (Upstash) with consumer groups; Temporal Cloud
   for durable workflows.
5. **Container images:** multi-stage Docker (`backend/Dockerfile`,
   `infra/Dockerfile.backend` for staging mirror).
6. **CI is GitHub Actions.** Required gates today: tenancy isolation,
   eval regression, secret scan, OpenAPI drift, dep audit (m12-pr04),
   coverage (m12-pr02).
7. **Staging mirror** (P1-15 SHIPPED) is `infra/staging-mirror.compose.yml`
   — runs the entire backend stack locally including Temporal-lite, Redis,
   Postgres, OTel collector. Used for any PR touching the runtime.
8. **Observability stack:** OTEL collector → Grafana Cloud (metrics +
   traces) + Sentry (errors) + Langfuse (AI traces).
9. **Feature flags** in `config/feature_flags.yaml` (file-driven; hot-
   reloadable). Per-org overrides via DB.
10. **Secrets** in Railway / Netlify env stores. `.env*` gitignored.
    Service role keys never exposed to frontend.
11. **Releases** are immutable container images by SHA. Rollback = redeploy
    a previous SHA. No mutating changes after deploy.
12. **Runbooks** live under `docs/runbooks/`. On-call page links them by
    alert name.

---

## Topology

```
                      Netlify (CDN + edge functions)
                          |   Next.js 14 SSR + ISR
                          |   www.hirestack.ai
                          v
                       https
                          |
                          v
                Railway (project: hirestack-prod)
   +-------------+-------------+----------------+----------------+
   |   api       |   worker    |   scheduler    | temporal_worker|
   |  uvicorn    |  RQ-style   |  cron-like     | Temporal SDK   |
   |  fastapi    |  consumer   |  ticker        | activities +   |
   |             |             |                | workflows      |
   +-----+-------+------+------+--------+-------+--------+-------+
         |              |               |                |
         |      Upstash Redis (streams + cache)          |
         |              |               |                |
         |      Supabase Postgres (managed)              |
         |              |               |                |
         |      Temporal Cloud (durable orchestration)   |
         |              |               |                |
         v              v               v                v
                  OTEL collector -> Grafana / Sentry / Langfuse
```

---

## Procfile

```
api: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers $WEB_CONCURRENCY
worker: python -m backend.app.worker
scheduler: python -m backend.app.scheduler
temporal_worker: python -m backend.app.temporal.worker
```

All four share the same image. Railway runs each as a separate dyno
(replica count tuned per env).

---

## Container images

`backend/Dockerfile` — production multi-stage:

1. `python:3.11-slim` builder; `pip install -r requirements.txt` into a
   wheel cache.
2. Final stage `python:3.11-slim` — copies wheels + source. No build
   tools in final image.
3. Non-root user (`app`).
4. `HEALTHCHECK CMD curl -f http://localhost:$PORT/healthz`.
5. Image labeled with git SHA + build timestamp.

`infra/Dockerfile.backend` is the staging-mirror variant (adds dev tools
+ `watchgod` for hot reload).

`frontend/Dockerfile` is used by the staging mirror only — production
frontend is built and deployed by Netlify directly from the repo.

---

## Staging mirror (P1-15 SHIPPED)

`infra/staging-mirror.compose.yml` brings up the entire backend stack on
a developer's laptop:

| Service | Image / build | Notes |
|---|---|---|
| `backend-api` | `infra/Dockerfile.backend` | hot-reloads on code changes |
| `backend-worker` | same image | runs queue consumer |
| `backend-scheduler` | same image | runs cron ticker |
| `backend-temporal-worker` | same image | connects to local temporalite |
| `frontend` | `frontend/Dockerfile` | Next dev server |
| `postgres` | `postgres:16` | seeded with `supabase/seed.sql` |
| `redis` | `redis:7-alpine` | streams + cache |
| `temporalite` | `temporalio/temporal:latest` (single-node mode) | local Temporal |
| `otel-collector` | `otel/opentelemetry-collector` | exports to local stdout / Jaeger |
| `jaeger` | `jaegertracing/all-in-one` | local trace UI |

```
make staging-mirror-up      # bring up
make staging-mirror-down    # tear down
make staging-mirror-logs    # tail logs
```

Any PR that touches `pipeline_runtime.py`, the worker, or Temporal
workflows MUST run a `staging-mirror-up` smoke test before merge.

---

## Railway (production) — per-service env

| Service | Min replicas | Scaling trigger | Notes |
|---|---|---|---|
| `api` | 2 | 70% CPU sustained 5m | rolling deploy |
| `worker` | 2 | queue depth > 200 | scale on consumer-group lag |
| `scheduler` | 1 | n/a | leader-locked via Postgres advisory lock |
| `temporal_worker` | 2 | queue depth > 50 | tracks Temporal task-queue backlog |

Health checks: `/healthz` for `api`; for workers, a heartbeat row in
`worker_heartbeats` table.

---

## Netlify (frontend)

- Build command: `cd frontend && npm ci && npm run build`.
- Publish directory: `frontend/.next`.
- Next.js 14 SSR + ISR via `@netlify/plugin-nextjs`.
- Branch deploys for every PR (preview URL).
- Env: `NEXT_PUBLIC_API_BASE_URL` per env; Supabase anon key per env.
- Edge functions: `frontend/netlify/edge-functions/` (auth bridge for
  preview deploys).

---

## Temporal Cloud

- Namespace: `hirestack-prod`. Staging in `hirestack-staging`.
- Task queues:
  - `pipeline` — primary GenerationWorkflow + activities
  - `eval` — nightly EvalRegressionWorkflow
  - `partition` — PartitionRotationWorkflow
  - `archive` — EventArchiveWorkflow
  - `interview` — LongLivedSessionWorkflow
- Worker fleet split per task queue. Polling concurrency set per worker.
- TLS client cert auth from Railway → Temporal Cloud.

---

## Redis (Upstash)

Single global cluster (Stage A). Stage B will introduce per-cell shards.

Key namespaces:

| Prefix | Purpose |
|---|---|
| `stream:pipeline.*` | Redis Streams for queue (with consumer groups) |
| `cache:prompt:*` | prompt cache (24h TTL) |
| `cache:rag:*` | embedding cache |
| `idempotency:*` | dedupe nonces (30s) |
| `slowapi:*` | rate-limit token buckets |
| `lock:*` | advisory locks (e.g. scheduler leader) |
| `dlq:*` | dead-letter queue indexing |

DLQ flow: a stream entry that fails N times (default 5) is XADDed to a
parallel `dlq:<stream>` and removed from the main stream. The DLQ inspector
endpoint (`/admin/dlq`) lists entries; replay on confirmation.

---

## Supabase

- Postgres 16, default connection pool via PgBouncer.
- 61 migrations applied via Supabase CLI (`supabase db push`).
- RLS on all multi-tenant tables (64/64 today).
- `pg_partman` extension for monthly partitioning of `audit_logs`,
  `ai_invocations`, and per-stage activity tables.
- `pg_cron` for hourly rollups (`org_cost_hourly`) and partition rotation.

`scripts/run_migrations.py` is the local helper; CI uses Supabase CLI.

---

## CI (GitHub Actions)

Workflows under `.github/workflows/`:

| Workflow | Required? | What it does |
|---|---|---|
| `backend-tests.yml` | yes | pytest -n auto, all backend tests |
| `frontend-tests.yml` | yes | vitest + tsc + lint |
| `e2e.yml` | yes (PR-touching frontend) | Playwright headless |
| `tenancy-isolation.yml` | yes | runs `tests/security/test_tenancy_isolation.py` exclusively |
| `eval-regression.yml` | yes | runs eval gold sets for chains touched in the PR |
| `secret-scan.yml` | yes | gitleaks |
| `openapi-drift.yml` | yes | regenerates `frontend/src/lib/api/generated/`; fails if diff |
| `dep-audit.yml` | yes (m12-pr04) | `pip-audit` + `npm audit` |
| `coverage.yml` | yes (m12-pr02) | enforces backend ≥ 75%, frontend ≥ 70% |
| `import-linter.yml` | yes | `lint-imports` per `pyproject.toml` |
| `migrations-check.yml` | yes | dry-run against ephemeral Postgres |

Reviewers may not bypass required checks. New required gates require an
ADR.

---

## Feature flags

`config/feature_flags.yaml`:

```yaml
ff_inprocess_fallback:
  default: false
  prod: false
  description: |
    Allow in-process pipeline execution when Temporal AND Redis are unavailable.
    Production MUST be off (single-process loss = data loss).
ff_anthropic_provider:
  default: true
  description: Use Anthropic when Gemini circuit breaker is open.
ff_strict_critic_gate:
  default: false
  description: |
    Sentinel hard-fails generation when factual issues are found.
    Off by default (warn-only) to avoid false positives.
ff_per_org_cost_cap:
  default: true
  description: usage_guard enforces per-org daily $ cap (P0-4).
# ... ~30 flags in total
```

Flags are read at module init + reloaded via SIGHUP. Per-org overrides
via `org_feature_flag_overrides` table.

---

## Observability (handoff)

See [PERFORMANCE_CONTEXT.md](PERFORMANCE_CONTEXT.md) for SLOs and
[KNOWN_ISSUES.md](KNOWN_ISSUES.md) for top alerts.

Endpoints:

- Grafana Cloud: dashboards `hirestack-api`, `hirestack-pipeline`,
  `hirestack-worker`.
- Sentry: project `hirestack-backend`, `hirestack-frontend`.
- Langfuse: project `hirestack-prod` (per-call AI traces).
- OpenTelemetry: collector at `infra/observability/otel-collector.yaml`.

---

## Runbooks

Under [docs/runbooks/](../docs/runbooks/):

| Runbook | When to use |
|---|---|
| `pipeline-stuck.md` | a job stays in `running` past 10m |
| `provider-outage.md` | Gemini or Anthropic returning 5xx surge |
| `partition-rotation-failed.md` | `pg_cron` partition job alert |
| `dlq-grew.md` | DLQ depth alert |
| `cost-runaway.md` | per-org cost cap repeatedly hit |
| `temporal-worker-down.md` | task-queue backlog growth |

Every alert in Grafana includes a `runbook_url` annotation.

---

## Releases

Per [RELEASE.md](../RELEASE.md):

1. Open PR; CI green; reviewer approves.
2. Merge to `main` → auto-deploys backend (Railway) and frontend (Netlify).
3. Backend deploy is blue/green by Railway: new image goes live; old
   replicas drain over 60s.
4. Tagged release notes are appended to [CHANGELOG.md](../CHANGELOG.md).
5. PR ledger updated under `/memories/repo/m<N>-pr<NN>-shipped.md`.
6. Rollback: redeploy previous SHA via Railway dashboard or `railway up
   --service <s> --image <sha>`.

---

## Backups + DR (Stage A)

- Supabase point-in-time recovery (PITR) — 7 days.
- `audit_logs` partitions exported to S3 Parquet monthly via
  `EventArchiveWorkflow`.
- `ai_invocations` partitions exported quarterly.
- Test restore quarterly (manual; runbook `dr-restore.md`).

Stage B introduces per-cell isolation + read-replica failover.

---

## What "good infra" looks like in this repo

- [ ] New service has a Procfile entry, a healthcheck, and an alert.
- [ ] New env var documented in [`docs/runbooks/env-vars.md`](../docs/runbooks/).
- [ ] New container has a non-root user.
- [ ] New CI gate has an ADR if it becomes required.
- [ ] New migration is reversible (`down.sql` if non-trivial).
- [ ] New cron has a leader lock (Postgres advisory) or is idempotent.
- [ ] No mutating "fix it in prod" workflow — change image and redeploy.
- [ ] Runbook exists for every page-level alert.
