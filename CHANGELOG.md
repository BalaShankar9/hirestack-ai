# Changelog

All notable changes to HireStack AI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The single source of truth for the **current** version is `backend/VERSION`
(consumed by `backend.app.core.config.Settings.app_version` and emitted on
the `/health` endpoint and Sentry `release` tag).

## [Unreleased]

### Added
- S12 (QA & Release Engineering) — `CHANGELOG.md`; `backend/VERSION` source
  of truth; Vitest + pytest coverage threshold gates; `pytest-timeout` in
  `backend/requirements.txt`; `RELEASE.md` runbook; ADR-0014.
- S11 (Observability & SRE) — structlog JSON pipeline with
  `redact_event_dict` processor; `app/core/observability.py`
  (`SENSITIVE_KEYS`, `sentry_before_send`); request-id correlation via
  `RequestIDMiddleware`; `/metrics` Bearer-token gate
  (`settings.metrics_auth_token`); SLO YAML alert manifest in `docs/SLO.md`;
  ADR-0013.
- S10 (Infra & Deploy) — canonical `infra/docker-compose.yml`; pinned
  Procfile entrypoint; deploy-gate uses `scripts/health_check.py`; pinned
  `/health` + `/openapi.json` shape; secret-scan now catches Supabase JWTs;
  ADR-0012.
- S1–S9 (Foundations through Pipeline) — see `docs/audits/` and
  `/memories/repo/` per-squad files for full ledgers.

### Changed
- (S11) Sentry init now passes `release=settings.app_version` and
  `before_send=sentry_before_send`.
- (S10) `docker-compose.yml` at repo root removed in favour of
  `infra/docker-compose.yml`.

### Security
- (S11) `/metrics` is fail-closed (403) in production when
  `METRICS_AUTH_TOKEN` is unset.
- (S11) Log + Sentry events scrub `password|token|api_key|authorization|
  secret|cookie|session|refresh_token|access_token|service_role_key|
  client_secret|private_key|...` from any nested dict/list (depth 8).
- (S10) Secret-scan extended with Supabase JWT pattern.

## [1.0.0] — 2026-04-20

Initial production-readiness baseline established by squads S1–S10.
See `/memories/repo/HIRESTACK_MASTER_JOURNAL.md` for the full pre-S11
release history.

[Unreleased]: https://github.com/hirestack-ai/hirestack-ai/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/hirestack-ai/hirestack-ai/releases/tag/v1.0.0
