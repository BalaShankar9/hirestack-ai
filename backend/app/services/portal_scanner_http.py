"""Production httpx-backed Fetcher for portal_scanner_worker.

The worker (services/portal_scanner_worker.py) accepts an injected
``Fetcher = Callable[[str], Awaitable[FetchResult]]`` so tests can run
without sockets.  This module supplies the **production** Fetcher that
talks to real ATS endpoints over HTTP.

Design
------
* GET-only.  Every endpoint canonicalised by ``portal_scanner.plan_fetches``
  serves JSON over GET.  (Workday's cxs endpoint also accepts POST with
  a filter body but the GET default suffices for the listing-only use
  case the worker supports today.)

* Returns ``FetchResult`` for **non-200** status codes — the worker
  decides which are retryable (429, 5xx) vs permanent (other 4xx)
  via its own ``_is_retryable_status`` helper.  Raising on every
  4xx would force the worker to grow special-casing it doesn't need.

* Raises ``FetchError`` (worker-defined) only for **transport** failures
  (connect timeout, DNS, TLS, read timeout, request error).  The worker
  treats those as retryable transient failures.

* JSON parse failure on a 200 response → ``FetchResult(status=200,
  payload=None, error="invalid_json")``.  The worker's ``_scan_one``
  hands that to the parser, which gracefully returns an empty list,
  and we get a ``parse_error`` failure entry — exactly the same
  treatment as a parser exception.

* Optional injected ``httpx.AsyncClient`` for the rare caller that
  wants to share a connection pool across many ``run_scan`` calls.
  Default is one-shot client per request — same pattern as
  ``batch_generate._live_httpx_fetcher`` so we don't surprise ops
  with a different connection-management model in the same codebase.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from app.services.portal_scanner_worker import FetchError, FetchResult, Fetcher

# ── Constants ────────────────────────────────────────────────────────

# Conservative default — ATS endpoints are usually fast (<2s) but
# Workday tenants can be slow during business hours.  The worker
# applies its own bounded retry on top so we don't need a generous
# per-request timeout.
DEFAULT_TIMEOUT_S: float = 15.0

# Identifies HireStack to the ATS.  We don't pretend to be a browser —
# the endpoints we hit are documented public job APIs, not scraped
# careers pages.
DEFAULT_USER_AGENT: str = "HireStackBot/1.0 (+https://hirestack.ai)"

# Hard cap on response body we'll parse as JSON.  Realistic worst
# case is Workday tenants returning ~2-3 MB; 8 MB gives margin without
# letting a malformed endpoint exhaust memory.
MAX_BODY_BYTES: int = 8 * 1024 * 1024


# ── Public factory ───────────────────────────────────────────────────


def make_httpx_fetcher(
    *,
    client: Optional[httpx.AsyncClient] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Fetcher:
    """Return a Fetcher that performs real HTTP GETs via httpx.

    Parameters
    ----------
    client:
        Optional pre-built ``httpx.AsyncClient`` to reuse across calls
        (recommended for long-running workers — saves the per-request
        TLS handshake cost).  When ``None`` we create a one-shot client
        per call, which mirrors ``batch_generate._live_httpx_fetcher``.
    timeout_s:
        Per-request timeout.  Applies to the full GET (connect + read).
    user_agent:
        Sent as the ``User-Agent`` header.  Defaults to a HireStack
        identifier so ATS owners can identify us in their access logs.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }

    async def _fetch(url: str) -> FetchResult:
        try:
            if client is not None:
                resp = await client.get(url, headers=headers, timeout=timeout_s)
            else:
                async with httpx.AsyncClient(
                    timeout=timeout_s,
                    follow_redirects=True,
                    max_redirects=3,
                    headers=headers,
                ) as one_shot:
                    resp = await one_shot.get(url)
        except httpx.HTTPError as exc:
            # All httpx transport-level failures (connect, read, write,
            # pool, timeout, TLS) inherit from HTTPError.  The worker
            # treats FetchError as retryable.
            raise FetchError(f"transport: {type(exc).__name__}: {exc}") from exc

        status = resp.status_code

        if status != 200:
            # Worker decides retry vs permanent based on status code.
            return FetchResult(
                status=status,
                payload=None,
                error=f"http_{status}",
            )

        # 200 — parse JSON.  We don't trust the Content-Type header
        # because some ATS endpoints serve JSON as text/plain.
        body = resp.content
        if len(body) > MAX_BODY_BYTES:
            return FetchResult(
                status=200,
                payload=None,
                error="body_too_large",
            )
        try:
            payload = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            return FetchResult(
                status=200,
                payload=None,
                error="invalid_json",
            )

        return FetchResult(status=200, payload=payload, error=None)

    return _fetch
