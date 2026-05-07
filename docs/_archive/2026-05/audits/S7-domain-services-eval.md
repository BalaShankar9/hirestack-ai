# S7 — Domain Services Audit

**Squad scope**: `backend/app/services/*` excluding S3 runtime files
(`pipeline_runtime.py`, etc.). 40 services total; this audit picks
the 5 with the highest blast-radius and zero or thin test coverage.

**Already covered (closed by prior squads)**:

- `pipeline_runtime.py`, `event_bus_bridge.py` — S3.
- `quality_scorer.py`, `usage_guard.py`, `document_catalog.py` — pre-S6.
- `webhook.py` retry path — `test_webhook_retry.py` (S2).
- `billing.py` feature flag — `test_billing_feature_flag.py`.

## Risk inventory

| ID  | Service                     | Risk                                                                                                               | Severity |
| --- | --------------------------- | ------------------------------------------------------------------------------------------------------------------ | -------- |
| R1  | `export.py`                 | Unicode/RTL/oversized inputs untested; HTML→text strip + entity handling has never been pinned.                    | HIGH     |
| R2  | `ats.py`                    | Extended-column fallback path is the production safety valve; if it ever raises, the AI score is still returned.   | HIGH     |
| R3  | `webhook.py`                | Slack-vs-generic body shape, signature computation, and event-filter (`*` and explicit list) gates are uncovered.  | HIGH     |
| R4  | `social_connector.py`       | URL parsing for github/linkedin/twitter and SSRF block list (private nets + AWS metadata) is security-critical.    | CRITICAL |
| R5  | `job_sync.py`               | Match-score record shape (defaults when AI returns nothing) and singleton getter are uncovered.                    | MEDIUM   |
| R6  | `export.py` markdown branch | Markdown output is the simplest fallback; trivial but uncovered, and the title escape rule is implicit.            | MEDIUM   |

## Charter checklist

- [ ] R1: pin `_strip_html`, `generate_docx_from_html`, markdown branch, oversized handling.
- [ ] R2: pin ats `_BASE_COLUMNS` invariant, fallback record shape, scan-id propagation when DB fails.
- [ ] R3: pin webhook `_is_slack_url`, `_format_slack_payload` (color flip on `failed`, key allow-list, payload truncation), HMAC signature determinism.
- [ ] R4: pin `_extract_github_username`, twitter handle normalisation, linkedin URL gate, website SSRF block list (loopback, RFC1918, link-local incl. 169.254 AWS metadata, IPv6 ULA + loopback).
- [ ] R5: pin `score_match` record defaults + `get_job_sync_service` singleton.
- [ ] Sign-off ADR-0009 codifying domain-service contract surface.

## Out of scope (deferred)

- Stripe webhook idempotency reconciliation — requires Stripe SDK fixtures; tracked but deferred to a billing-focused mini-squad.
- ATS golden set benchmarking — requires curated CV/JD pairs; tracked separately.
- `social_connector.py` per-call backoff — `httpx` retry middleware would change the source signature; deferred indefinitely.
- `job_sync.py` AI-call backoff — same reason.
- 35 other services with thin coverage but lower blast radius (most are CRUD).

## Test runner

```
cd "/Users/balabollineni/HireStack AI/backend" && \
PYTHONPATH="$PWD:$PWD/.." \
"/Users/balabollineni/HireStack AI/.venv/bin/python" -m pytest tests/unit -q
```

Pre-S7 baseline: 1552 passed in 6.47s.
