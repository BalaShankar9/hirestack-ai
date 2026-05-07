# S11 — Observability & SRE — Audit (2026-04-21)

Surveyed: `backend/main.py`, `backend/app/core/{tracing,metrics}.py`, `docs/SLO.md`, `.github/workflows/*.yml`, structlog/Sentry/slowapi config.

## Existing surface (good, do not regress)

- ✅ Structlog JSON logging w/ `_add_request_id` processor injecting `X-Request-ID` from contextvar.
- ✅ `RequestIDMiddleware` (pure ASGI; SSE-safe; honours upstream header; caps length 128; emits same header on response).
- ✅ `AccessLogMiddleware` (timing, status, request_id; skips `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`).
- ✅ `MaxBodySizeMiddleware`, `TimeoutMiddleware`, `SecurityHeadersMiddleware`.
- ✅ Sentry init when `settings.sentry_dsn` truthy. `traces_sample_rate=0.1` in prod / `1.0` elsewhere. `send_default_pii=False`.
- ✅ `MetricsCollector` + `/metrics` Prometheus text-exposition endpoint with pipeline counts, p50/p95, phase latency, doc quality.
- ✅ `slowapi` per-user rate limiter on key routes; `429` exception handler installed.
- ✅ `docs/SLO.md` exists.
- ✅ `backend/tests/unit/test_perf_optimizations.py` — pins `/metrics` exposes cache + per-phase gauges.
- ✅ `backend/tests/unit/test_observability.py` — pins PipelineMetrics summary shape.

## Risk register (S11)

| ID | Severity | Risk | Evidence | Fix wave |
|---|---|---|---|---|
| **R1** | **P0** | `/metrics` is unauthenticated and `include_in_schema=False`. Anyone hitting prod can read pipeline counters, model failovers, queue depth. Information disclosure. | `backend/main.py` line 381 — `@app.get("/metrics", tags=["Observability"], include_in_schema=False)`, no `Depends`, no token check. | F1 |
| **R2** | **P1** | No log redaction. Free-form `logger.info(...)` calls everywhere; if a downstream service ever returns `{token: ...}` and we log the dict, it lands in stdout/Sentry. No structlog processor scrubs `password|token|api_key|authorization|secret|cookie` keys. | grep for `redact|REDACTED|before_send` — zero matches in production code. | F2 |
| **R3** | **P1** | Sentry `before_send` hook is missing. The default scrubber is on but doesn't cover request bodies for FastAPI auto-instrumentation. JWTs in headers will be scrubbed by `send_default_pii=False`, but URL query strings (e.g., `?token=...`) are not. | `backend/main.py` Sentry init has no `before_send` callable. | F2 |
| **R4** | **P1** | No request_id propagation test; no test that the `X-Request-ID` header round-trips and appears in structlog output. A future middleware reorder could silently break correlation. | `backend/tests/` grep — no `test_request_id*`. | F3 |
| **R5** | **P2** | `RequestIDMiddleware` registered AFTER `AccessLogMiddleware` (AccessLog reads `request_id_var.get("")` which would be empty if RequestID hasn't run yet — but Starlette runs middleware in REVERSE order, so this actually works. Worth a regression test pinning the order. | `backend/main.py` lines 315–316 — `add_middleware` order reads odd at first glance. | F3 |
| **R6** | **P2** | Sentry env scoping: `environment=settings.environment` is good; missing `release=settings.app_version` so Sentry can't bisect by deploy. | `backend/main.py` line 36. | F2 |
| **R7** | **P2** | No alert manifest — `docs/SLO.md` exists but there is no machine-readable contract describing thresholds (e.g., p95 latency, error rate, queue depth) that on-call should page on. | Confirmed by reading `docs/SLO.md`. | F4 (docs only — not behavioural) |
| **R8** | **P3** | `MetricsCollector` global singleton (`MetricsCollector.get()`); per-test isolation depends on whether tests reset it. | F0 survey. | Accepted (already covered by existing tests) |
| **R9** | **P3** | `/metrics` builds the response by repeatedly importing modules inside a try block (laziness). One bad import would silently miss a section. | `backend/main.py` lines 391–540. | Accepted |
| **R10** | **P3** | No Grafana / Prometheus scrape-config in repo. Operations concern; out of scope for behavioural CI. | F0 survey. | Accepted |

## Fix-wave plan

- **F1** — `/metrics` requires auth (env-driven bearer token). Default behaviour: open in `debug=True`/dev, locked in `production`. Tests pin the auth contract.
- **F2** — Structlog redaction processor + Sentry `before_send` scrubber + `release=app_version`. Tests pin redaction key list and sample payload masking.
- **F3** — Tests pinning `X-Request-ID` round-trip + middleware order regression guard.
- **F4** — Augment `docs/SLO.md` with a single machine-readable YAML block (alert thresholds), and add ADR-0013 + sign-off. No new code.

## Out of scope (forwarded)
- Grafana dashboards, Prometheus scrape configs, alertmanager — operations.
- OpenTelemetry tracing — separate vendor decision.
- Frontend Sentry config — covered in mobile/frontend squads.
