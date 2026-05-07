# HireStack AI — Architecture

> Canonical, single-source description of the HireStack AI system as it exists
> today and the **target** topology being delivered across milestones M1–M6.
> When this document and any other doc disagree, **this document wins**.

---

## 1. Mission

HireStack AI helps candidates run their job search as a structured operation:
sourcing roles, generating tailored application materials, tracking outreach,
and learning from outcomes. The platform is multi-tenant (org-scoped),
LLM-powered, and event-driven.

---

## 2. Deployables (target topology)

The system runs as **four** independently scalable processes plus managed
services. No Kubernetes, no service mesh — Fly.io / Railway machines + Vercel.

| Process            | Purpose                                                                                  | Scale model                |
| ------------------ | ---------------------------------------------------------------------------------------- | -------------------------- |
| `api`              | FastAPI HTTP surface. Stateless. Multi-replica.                                          | Horizontal, ≥ 2 replicas   |
| `worker`           | Redis Streams consumer. Runs outbox relay, event consumers, async jobs.                  | Horizontal, N consumers    |
| `scheduler`        | Singleton process. Cron-style jobs (cleanup, watchdog, partition rotation, TTL sweeps). | Singleton via leader lock  |
| `temporal_worker`  | Temporal activity/workflow worker. Owns durable generation pipeline.                     | Horizontal, task-queue bound |
| `web` (frontend)   | Next.js 14 app. SSR + client.                                                            | Vercel/Netlify edge        |

Today only `api` and `web` exist as discrete processes; `worker`, `scheduler`,
and `temporal_worker` are extracted in M2 and M6 respectively.

---

## 3. Data plane

| Store                | Role                                                              | Notes                                       |
| -------------------- | ----------------------------------------------------------------- | ------------------------------------------- |
| Postgres (Supabase)  | System of record. Multi-tenant via RLS keyed on `org_id`.         | Adds `pgvector` in M6 PR-19.                |
| Postgres `events_outbox` | Transactional outbox for domain events.                       | Partitioned by month. Added in M3 PR-8.     |
| Redis Streams        | Event bus, async job queue, idempotency cache.                    | Single-region, single instance.             |
| Object storage       | Generated artifacts (PDFs, decks, audio).                          | Presigned URLs only.                        |
| Langfuse             | LLM trace + evaluation store.                                      | Self-hosted or SaaS.                        |
| OTEL collector       | Application traces + metrics.                                      | Honeycomb / Tempo / Grafana Cloud.          |

**No Kafka. No NATS. No event sourcing.** Outbox + idempotent consumers only.

---

## 4. Domain boundaries

The backend is organized as a **modular monolith**. Domains never cross-import.

```
backend/app/
  api/                # HTTP routers grouped by domain
  services/
    aim/              # AIM (Application Intelligence Module)
    missions/         # mission control / cadence / outreach
    generate/         # generation orchestration
    job_sync/         # external job ingest
    tracking/         # tracked companies / portal scanners
  workers/            # Redis-Streams consumers + outbox relay
  scheduler/          # cron jobs (singleton)
  core/               # cross-cutting: config, db, telemetry, events, idempotency
  temporal/           # workflow definitions + activities (M6)
ai_engine/            # LLM-facing logic. Imported by backend ONLY via ai_engine.api
```

A custom lint rule (added in M4 PR-11) enforces:

- `from app.services.X` cannot import `from app.services.Y`.
- `from ai_engine.X import Y` outside `ai_engine.api` is a lint error in `backend/`.

---

## 5. AI runtime

`ai_engine/` is the only place where prompts, model routing, and agent control
flow live. Backend talks to it through a single stable surface: `ai_engine/api.py`.

Pipeline shape (target, after M6):

1. **Plan** — `ai_engine.agents.planner.plan(req)` produces an ordered step list.
2. **Execute** — each step is an activity inside a Temporal `GenerationWorkflow`.
3. **Critique** — `ai_engine.agents.critic.critique(step, result)` gates persistence.
4. **Persist** — domain artifacts written to Postgres in same tx as outbox event.
5. **Emit** — `generation.step.completed` / `generation.completed` published via outbox.

Tools are dispatched through a **DB-backed registry** (`ai_tools`,
`ai_agent_tool_grants`) added in M5 PR-14. Agents cannot call arbitrary code;
the dispatcher enforces input/output schemas, auth scope, and granted-tool
allow-listing.

---

## 6. Event-driven architecture

```
domain write tx
   ├── INSERT domain row
   └── INSERT events_outbox row    ← same tx, atomic
                │
                ▼
       outbox_relay (worker)        ← M3 PR-9
                │  XADD events:{type}
                ▼
         Redis Streams
                │
         consumer groups            ← M3 PR-10
                ├── billing_usage
                ├── aim_source_embed   (M6 PR-19)
                ├── generation_status  (M6 PR-18)
                └── ...
```

Every consumer is **idempotent** (writes to `consumed_events (consumer, event_id)`
before acting). After N failures, events move to `events_dlq`.

Initial event types (M3 PR-8): `aim.assignment.created` v1, `aim.source.created`
v1, `generation.requested` v1, `generation.completed` v1,
`mission.draft.created` v1.

---

## 7. Observability

- **Tracing:** OpenTelemetry (FastAPI auto-instrumentation + manual spans on
  background jobs and event consumers). Each span carries `request_id`,
  `org_id`, `job_id` where applicable.
- **LLM:** Langfuse trace per LLM call: `model`, `prompt_id`, `tokens`, `cost`,
  `latency`, eval scores.
- **Logs:** structlog JSON to stdout; aggregated by platform (Fly/Railway).
- **Errors:** Sentry on `api`, `worker`, `scheduler`, `temporal_worker`, `web`.
- **Metrics:** OTEL → Honeycomb/Tempo. SLOs in `docs/SLO.md`.

---

## 8. Security model

- **Tenancy:** Postgres RLS on every multi-tenant table keyed on `org_id`.
  CI test (`backend/tests/security/test_tenancy_isolation.py`, M1 PR-4) walks
  every authenticated route and asserts cross-org reads return 403/404.
- **Idempotency:** `Idempotency-Key` middleware on POST/PATCH/DELETE
  (M1 PR-3). Backed by `idempotency_keys` table with 24h TTL sweep.
- **SSRF guard:** `safe_fetch` (M5 PR-15) DNS-resolves and blocks RFC1918,
  link-local, loopback, and cloud metadata IPs. All outbound LLM-driven
  fetches go through it.
- **Prompt-injection defense:** user input is delimited and labeled as data
  (M5 PR-16). Critic gate is mandatory for trust-critical artifacts (AIM).
- **Secrets:** environment-only. Secret-scan job in CI.
- **AuthN/Z:** Supabase JWT → `get_current_user` dependency → org-scoped
  service calls.

---

## 9. Frontend

- Next.js 14 App Router, React 18, TypeScript, Tailwind, Radix, TanStack
  Query v5.
- Hand-rolled `frontend/src/lib/api.ts` is being **strangled** by an
  OpenAPI-generated SDK (M4 PR-13, then continuous Track A).
- Heavy dependencies (`pdfjs-dist`, `html2pdf.js`, `mammoth`, `html2canvas`)
  are dynamically imported on the routes that need them (Track D).

---

## 10. CI / CD

Required CI jobs (all must be green to merge):

- Lint (ruff, eslint, tsc).
- Unit + integration tests (backend pytest, frontend vitest, e2e Playwright on
  smoke flow).
- Tenancy isolation test (M1 PR-4).
- Eval gate (`ai_engine/evals/`).
- Secret scan.
- OpenAPI SDK drift check (M4 PR-13).

Deployment is push-based: `main` → staging auto-deploy → manual promote to prod.

---

## 11. Feature flags

All risky or user-visible changes ship behind a flag prefixed `ff_`. Default is
**off** unless the PR description says otherwise. Flags are reversible without
code changes. Notable flags introduced by the M1–M6 plan:

- `ff_outbox_relay`
- `ff_tool_registry`
- `ff_strict_critic_gate`
- `ff_temporal_generation`
- `ff_aim_rag`

---

## 12. What we are explicitly NOT doing

- No Kubernetes (Fly/Railway machines + Vercel until 100k MAU).
- No Kafka / NATS (Redis Streams through Q3 minimum).
- No microservices beyond the four deployables above.
- No GraphQL / gRPC (REST + OpenAPI only).
- No event sourcing (outbox + idempotent consumers).
- No multi-region in Q1.

---

## 13. References

- ADRs: `docs/adrs/`
- Runbooks: `docs/runbooks/`
- SLOs: `docs/SLO.md`
- Project journal: `docs/PROJECT_JOURNAL.md`
- Build execution plan: see PR descriptions for M1–M6.
