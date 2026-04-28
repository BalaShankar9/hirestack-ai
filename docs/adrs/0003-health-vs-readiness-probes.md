# ADR-0003: Three health endpoints — `/livez`, `/healthz/ready`, `/health`

Status: Accepted — 2026-04-21 (S1-F11)
Owners: Platform Core squad

## Context

The original `main.py` exposed two endpoints:

- `/livez` — cheap event-loop probe (no dependencies).
- `/health` — full diagnostic snapshot: Supabase ping + AI key
  check + Redis ping + circuit-breaker state + model_router health
  + metrics summary + queue depth.

`/health` returns within ~5–8 s when everything is healthy and up
to ~30 s during an outage (waits on Supabase / Redis timeouts plus
ai_engine introspection). Using it as a Kubernetes readiness probe
caused two problems:

1. **Noisy restarts** — slow `/health` responses tripped probe
   timeouts, the orchestrator marked the pod NotReady, and traffic
   moved to other replicas which then drowned in load.
2. **Wrong contract** — readiness gating must reflect "can this pod
   serve traffic right now". `/health` includes signals (model
   availability, queue depth, AI key presence) that are useful for
   operators but not preconditions for serving traffic.

## Decision

Adopt the conventional three-endpoint split:

| Endpoint            | Audience              | Touches                                            | SLA target |
|---------------------|-----------------------|----------------------------------------------------|------------|
| `/livez`            | Liveness probe        | Event loop only                                    | <50 ms     |
| `/healthz/ready`    | Readiness probe       | Supabase (2 s timeout), Redis (1 s timeout)        | <2.5 s     |
| `/health`           | Operators, dashboards | Everything: Supabase, AI key, Redis, breakers, model_router, metrics, queue | <30 s |

All three live in `app/api/routes/health.py` and are mounted via
`app.include_router(health_router)`.

### Readiness contract

- 200 + `{"status": "ready"}` iff Supabase is reachable.
- Redis being unreachable returns `{"connected": false, "fallback": "in_memory"}`
  but does **not** flip readiness to 503 — the in-memory cache
  fallback is acceptable for serving traffic (see ADR-0002).
- 503 + `{"status": "not_ready"}` if Supabase is unreachable.
- Test pin: `test_readiness_does_not_touch_ai_or_breakers` ensures
  the source code never references `model_router`, `_breakers`,
  `MetricsCollector`, `queue_depth`, or `ai_engine`.

### Production exposure

`/health` returns only `{status, version}` in production unless
`DEBUG=true` — internal state (breaker failure counts, queue
depth) is not exposed publicly.

## Consequences

- Orchestrators (Railway, Kubernetes, etc.) gate on `/healthz/ready`.
  Within 30 s of a Supabase incident the pod is marked NotReady and
  traffic is shed to healthy replicas (or to the static error page).
- `/livez` keeps containers alive; flaky DB does not cause restart
  loops that mask the underlying incident.
- `/health` remains the single source of truth for operators and
  dashboards.

## Alternatives considered

- **Single `/health` endpoint with fast/slow modes via query param** —
  rejected. Misuse-prone and breaks standard probe configs.
- **Separate `/healthz` and `/readyz`** (no `/healthz/ready`) —
  rejected for path consistency with the existing `/livez` and
  the namespaced `/healthz/*` family that future probes (e.g.
  `/healthz/startup`) can extend.
