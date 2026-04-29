# ADR-0009: Domain Services Contract Surface

**Status:** Accepted
**Date:** 2026-04-21
**Squad:** S7 — Domain Services
**Owners:** AI Engine + Platform

## Context

`backend/app/services/` ships 40 domain services consumed by the
HTTP layer, the pipeline runtime, and Stripe/webhook integrations.
Five of these own load-bearing security or correctness contracts
that downstream consumers (web clients, recruiters, monitoring)
depend on but that were not previously pinned by behavioural tests.

A change to any one — e.g. switching SSRF block list, dropping
`status="new"` from `score_match`, allowing numeric HTML entities
through `_strip_html` — would cause silent regressions that the
existing test suite would not catch.

This ADR codifies the public surface of those 5 services as
behavioural contract. Future changes must update the corresponding
test file in lock-step or be rejected at code review.

## Decision

### 1. `app.services.export.ExportService` (R1, R6)

Pure helpers (`_strip_html`, `_generate_markdown`, `_generate_pdf`,
`_generate_docx`) and the module-level `generate_docx_from_html`
form a sealed contract:

- HTML stripping decodes only `&nbsp;`, `&amp;`, `&lt;`, `&gt;`.
  Numeric entities `&#NNN;` are dropped to empty (intentional
  sanitisation of injected payloads).
- Markdown emission separates documents with `\n\n---\n\n`.
- PDF emission XML-escapes `& < >` before reportlab to prevent
  parser failures; empty list emits a `"No content to export."`
  placeholder paragraph.
- DOCX emission preserves Unicode/RTL/CJK/emoji and inserts a page
  break after each document.
- Format-dispatch surface accepts an unused `document_type` kwarg
  to maintain caller compatibility.

Pinned by [`backend/tests/unit/test_export_service.py`](../../backend/tests/unit/test_export_service.py)
(42 tests).

### 2. `app.services.ats.ATSService` (R2)

The base / extended column split is part of the operator contract:

- `_BASE_COLUMNS` (5 keys) and `_EXTENDED_COLUMNS` (14 keys) are
  exact and disjoint. New fields require a migration.
- Extended-column probe is cached at module level
  (`_extended_available`); failure is sticky (False survives
  subsequent calls).
- Field mapping is canonical:
  `readability_score ← score_breakdown.structure_score`,
  `format_score ← score_breakdown.strategy_score`.
- Fallback path: extended `db.create` fails → retry with
  `_BASE_COLUMNS`-only filtered record. Both fail → `id=None` but
  the AI scan result is **always** returned with `status="completed"`.

Pinned by [`backend/tests/unit/test_ats_service.py`](../../backend/tests/unit/test_ats_service.py)
(16 tests).

### 3. `app.services.webhook` (R3)

The Slack body + retry surface is consumer-facing:

- `_is_slack_url` matches `*.slack.com/services/*`, case-insensitive.
- `_format_slack_payload` emits a fixed-shape dict with the
  highlight-key allowlist `{application_id, job_title, company,
  status, score}` and a 3500-char attachment-text cap. `failed`
  in the event_type flips colour to `danger`.
- `_RETRY_MAX_ATTEMPTS = 3` and
  `_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}`
  are part of the operator monitoring contract — 4xx outside
  this set is **never** retried.
- HMAC-SHA256 over UTF-8 body bytes; deterministic for replay.

Pinned by [`backend/tests/unit/test_webhook_contract.py`](../../backend/tests/unit/test_webhook_contract.py)
(29 tests, supplements pre-existing `test_webhook_retry.py`).

### 4. `app.services.social_connector.SocialConnector` (R4 — CRITICAL)

Security-critical surface; SSRF block list is non-negotiable:

- Block list: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`, `169.254.0.0/16` (AWS metadata!), `::1/128`,
  `fc00::/7`. Any change requires a security review.
- DNS resolution happens **before** httpx request; `gaierror`
  surfaces as `ValueError("Could not resolve hostname")`.
- Schemeless URLs gain `https://` prefix before `urlparse`.
- GitHub regex `github\.com/([a-zA-Z0-9_-]+)/?$` is anchored —
  paths past the username (e.g. `github.com/user/repo`) return None.
- LinkedIn requires `linkedin.com/in/<slug>`; `/company/*` is
  rejected.
- Twitter normalises every input to `https://x.com/{handle}`.
- `CONNECT_TIMEOUT = 15s` (operator SLO).

Pinned by [`backend/tests/unit/test_social_connector.py`](../../backend/tests/unit/test_social_connector.py)
(56 tests).

### 5. `app.services.job_sync.JobSyncService` (R5)

Alert + match record shapes are downstream-visible:

- `create_alert` stores `salary_min=None` when the input is falsy
  (preserves nullable column semantics).
- `score_match` truncates description to 5000 chars in the DB row
  but only 2000 in the AI prompt (deliberate split).
- Records always begin with `status="new"`.
- `update_match_status` enforces ownership (returns False when the
  caller does not own the match) before issuing any update; the
  `"applied"` status additionally writes an ISO-8601 UTC
  `applied_at` timestamp.
- `get_job_sync_service()` is a process-wide singleton — repeated
  calls do **not** re-construct the AI client.

Pinned by [`backend/tests/unit/test_job_sync_service.py`](../../backend/tests/unit/test_job_sync_service.py)
(20 tests).

## Out of Scope (deferred to future squads)

- **Stripe idempotency:** belongs to a future Billing & Payments
  workstream (already mirrored to supabase/ in S2-F1+F2; the
  contract pinning is deferred).
- **ATS golden set:** the AI ranker accuracy is owned by the
  AI Engine evaluation harness, not domain services.
- **`social_connector` per-platform retry / backoff:** runtime
  resilience belongs to S11 Observability & SRE (operator-side
  alerts) plus future runtime hardening.
- **`job_sync` poller backoff:** same — defer to runtime hardening.

## Consequences

- **Positive:** any change to the listed surfaces forces an
  explicit test update, surfacing the contract break at PR review.
- **Positive:** SSRF block list and webhook retry policy are now
  visible to security/operator audits.
- **Cost:** +163 net new unit tests, +1.65s suite latency (6.47s
  pre-S6 → 8.12s post-S7, well under the 15s budget).

## References

- S7-F0 audit: [`docs/audits/S7-domain-services-eval.md`](../audits/S7-domain-services-eval.md)
- S7 sign-off: [`docs/audits/S7-domain-services-signoff.md`](../audits/S7-domain-services-signoff.md)
- Squad commits: 59bd90a (F0), 31f0c87 (F1), 5055955 (F2),
  1394c9c (F3), e2810f8 (F4), 7fb5dd9 (F5).
