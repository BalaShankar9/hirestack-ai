# ADR-0013 — Observability & SRE Contract Surface

**Status:** Accepted
**Squad:** S11 (Observability & SRE)
**Date:** 2026-04-21
**Supersedes:** none
**Related:** ADR-0003 (health vs readiness), ADR-0012 (infra & deploy)

## Context

S10 hardened the deploy gate but left four real observability risks open: `/metrics` was unauthenticated in production (R1), no log redaction existed (R2), Sentry had no `before_send` scrubber and no `release` pin (R3, R6), and there was no test pinning request-id propagation or middleware order (R4, R5). `docs/SLO.md` was prose-only — there was no machine-readable alert manifest (R7).

## Decision

The observability contract surface is:

| Concern | Canonical | Pinned by |
|---|---|---|
| Structured logging | `structlog` JSON renderer with processor chain ending in `redact_event_dict` then `JSONRenderer` | `tests/test_observability_redaction.py` |
| Sensitive-key markers | `app/core/observability.SENSITIVE_KEYS` (case-insensitive substrings) — single source of truth for both log scrubbing and Sentry scrubbing | same |
| Sentry init | `release=settings.app_version`, `before_send=sentry_before_send`, `send_default_pii=False`, `traces_sample_rate=0.1` in prod | same |
| Request correlation | `RequestIDMiddleware` (pure ASGI, SSE-safe, 128-char cap, generates 16-hex when missing, honours `X-Request-ID` upstream header, reflects on response) | `tests/test_request_id_propagation.py` |
| Middleware add-order | `RequestID → AccessLog → MaxBodySize → Timeout → SecurityHeaders` (Starlette executes in REVERSE so first add is outermost) | same |
| CORS exposure | `X-Request-ID` listed in `allow_headers` | same |
| Metrics endpoint | `/metrics` requires `Authorization: Bearer <settings.metrics_auth_token>`. In `production` an empty token returns 403; in dev/test it falls open. Constant-time compare via `hmac.compare_digest`. | `tests/test_metrics_auth.py` |
| SLO alert manifest | Single ```yaml fenced block in `docs/SLO.md` with required alerts + severity ∈ {`warn`, `page`} | `tests/test_slo_alert_manifest.py` |

## Consequences

### Positive
- `/metrics` cannot leak in prod without explicit token misconfiguration; misconfiguration fails closed (403) rather than open.
- Logs and Sentry events scrub `password|token|api_key|authorization|secret|cookie|session|refresh_token|access_token|service_role_key|client_secret|private_key|...` from any nested dict/list (depth-bounded at 8).
- Sentry releases are pinned to `app_version` so deploys are bisectable.
- A future refactor that drops `redact_event_dict`, `before_send`, `release=`, or reorders middleware will fail a behavioural test, not silently regress.
- SLOs are now machine-readable; alertmanager / Grafana provisioning can consume the YAML block directly.

### Negative
- Adding the `metrics_auth_token` setting means **operators MUST set it in production** before deploying S11 — this is intentional fail-closed behaviour, but it's a deploy-time gotcha.
- `redact_event_dict` walks every event_dict on every log call; bounded at depth 8, list-length 1000. Unmeasured but likely low single-digit microseconds per log line.
- The structlog scrubber matches by KEY substring, not value content. A free-form value like `"my password is hunter2"` logged under key `event` will not be redacted. Acceptable: developers should log secrets through dedicated keys, not embedded in messages.

### Deferred / Accepted Risk
- **R7 (no operational alert manifest)** — partially closed by the SLO YAML block; full Grafana / alertmanager provisioning lives outside this repo (operations).
- **R8/R9** (`MetricsCollector` global singleton, lazy section imports in `/metrics`) — accepted; existing tests cover both shapes.
- **R10** (no Grafana / Prometheus scrape config in repo) — operations concern.
- OpenTelemetry tracing — separate vendor decision; not blocked by S11.

## Verification

S11 shipped **56 new behavioural tests** across 5 fix-waves:

| Wave | Commit | Tests | Subject |
|---|---|---|---|
| F0 | `3913fdb` | 0 | 10-risk audit (`docs/audits/S11-observability-sre.md`) |
| F1 | `3c525d4` | 9 | `/metrics` Bearer-token gate + constant-time compare |
| F2 | (next) | 35 | Log redaction + Sentry `before_send` + `release` pin |
| F3 | `bf278d0` | 8 | Request-ID round-trip + middleware order regression |
| F4 | (this commit) | 4 | SLO alert manifest pin |

Backend suite: **1981 passed, 11 skipped** (post-S10: 1924 → +57). Frontend (335) + mobile (45) untouched.
