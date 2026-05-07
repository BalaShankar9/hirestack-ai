# S11 — Observability & SRE — Sign-Off

**Date:** 2026-04-21
**Squad lead:** GitHub Copilot (autonomous)
**Status:** ✅ Complete

## Scope

Close the 10 risks in `docs/audits/S11-observability-sre.md`. P0 was R1 (`/metrics` unauthenticated in prod). P1s were R2 (no log redaction), R3 (no Sentry `before_send`), R4 (no request-id propagation tests), R5 (middleware add-order unprotected), R6 (no Sentry release pin).

## Outcome

| Metric | Pre-S11 | Post-S11 | Δ |
|---|---|---|---|
| Backend tests | 1924 | 1981 | +57 |
| Backend skipped | 11 | 11 | 0 |
| Backend duration | 118.73s | 112.74s | -5.99s |
| Frontend tests | 335 | 335 | 0 |
| Mobile tests | 45 | 45 | 0 |
| P0 risks open | 1 (`/metrics` open) | 0 | -1 |
| P1 risks open | 5 | 0 | -5 |

## Fix-Wave Ledger

1. **F0 `3913fdb`** — `docs/audits/S11-observability-sre.md` (10-risk register).
2. **F1 `3c525d4`** — `/metrics` Bearer-token gate; new `settings.metrics_auth_token`; `_check_metrics_auth(request)` helper using `hmac.compare_digest`. (9 tests)
3. **F2 `7409a11`** — `app/core/observability.py` (`SENSITIVE_KEYS`, `redact_event_dict`, `sentry_before_send`); main.py adds redactor to structlog chain; Sentry init gains `release=app_version` and `before_send`. (35 tests)
4. **F3 `bf278d0`** — Request-ID round-trip + middleware add-order regression + CORS allow-headers guard. (8 tests)
5. **F4 (this commit)** — SLO alert manifest YAML block in `docs/SLO.md`; `tests/test_slo_alert_manifest.py` (4 tests). ADR-0013 + sign-off.

## Carried-Forward Risks

- R7 (operational alert manifest) — partially closed by SLO YAML; full Grafana/alertmanager provisioning is operations.
- R8, R9 (MetricsCollector singleton, lazy `/metrics` imports) — accepted.
- R10 (Grafana scrape configs) — operations.
- OTel tracing — separate decision.

## Out-of-Band Action

- **Operators must set `METRICS_AUTH_TOKEN` in the production environment** before deploying S11. Without it, `/metrics` returns 403 in prod (fail-closed by design).

## Gate Decision

**PROCEED to S12** (QA & Release Engineering).
