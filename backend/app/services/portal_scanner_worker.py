"""B1.next — portal_scanner_worker (async fetch glue).

The cron entrypoint that turns the pure-function ``portal_scanner``
into an end-to-end "scan all tracked companies, persist new postings"
pass.  Three responsibilities:

  1. Honour **per-provider rate limits** so we don't ratelimit-burn
     a public ATS API on a noisy cron.  Each provider has its own
     ``asyncio.Semaphore`` whose count is the platform-specific
     in-flight cap.
  2. **Exponentially back off** on transient failures (network
     errors, 429, 5xx) up to a small bounded retry count.  4xx other
     than 429 is permanent — we drop the plan and log.
  3. **Cap total concurrency** with an outer semaphore so a user
     tracking 200 companies doesn't open 200 sockets at once even if
     the per-provider limits would allow it.

What this module does NOT do:
  * No DB writes.  The caller persists the returned ``ScanRun`` —
    keeps the worker testable end-to-end without a Supabase mock and
    lets the cron decide whether to upsert into ``job_scan_history``
    or stream into a notification fan-out.
  * No URL-canonical dedup logic of its own.  Callers thread the
    pre-fetched ``seen_url_canonicals`` set into ``run_scan`` and the
    worker delegates to ``filter_new_postings``.
  * No HTTP client construction.  The fetcher is injected
    (``Fetcher = Callable[[str], Awaitable[FetchResult]]``) so tests
    pass a deterministic stub and the real cron passes an ``httpx.
    AsyncClient.get``-derived adapter.

HARD RULES:
  * Every awaited operation MUST be cancellable — no
    ``asyncio.shield`` of network work; cron may be killed mid-scan
    and we want clean teardown.
  * Backoff sleeps are awaited via the injected ``sleep`` callable
    (defaults to ``asyncio.sleep``) so unit tests run in milliseconds.
  * Per-provider rate limits are conservative.  Bumping them up is
    cheap; getting IP-banned from Greenhouse is not.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping, Optional, Sequence

from app.services.portal_scanner import (
    FetchPlan,
    JobPosting,
    Provider,
    filter_new_postings,
    parse_payload,
    plan_fetches,
    TrackedCompany,
)

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────


# Per-provider in-flight cap. Greenhouse and Lever publish public
# ATS APIs without auth; the others do too but we treat them as more
# fragile.  These are deliberately low — a typical user tracks <50
# companies so even a 2-wide concurrency clears in seconds.
_PROVIDER_CONCURRENCY: Mapping[Provider, int] = {
    "greenhouse":      4,
    "lever":           4,
    "ashby":           3,
    "workday":         2,
    "workable":        3,
    "smartrecruiters": 3,
}

# Outer cap regardless of provider mix — protects against tracking
# 200 companies all on Greenhouse from blowing past the host limit.
_GLOBAL_CONCURRENCY: int = 8

# Retry policy.  We retry on 429, 5xx, and any network exception
# bubbled up by the fetcher (raised as ``FetchError``).
_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0   # 1, 2, 4 seconds between attempts
_BACKOFF_MAX_SECONDS:  float = 8.0


# ── Public types ─────────────────────────────────────────────────────


class FetchError(Exception):
    """Raised by a Fetcher when the GET fails for transport reasons.

    The worker treats this as retryable.  4xx other than 429 should
    be returned as a ``FetchResult`` with the appropriate status
    code instead of raised, so the worker can mark them permanent.
    """


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one HTTP GET handed back from the injected fetcher.

    ``payload`` is the parsed JSON body (any shape) when status==200,
    otherwise None.  Callers should not mutate ``payload``.
    """
    status: int
    payload: object | None = None
    error: Optional[str] = None  # human-readable diagnostic for logs


# A pure-callable fetcher: takes a URL, returns a FetchResult.
# Implementations may raise FetchError for retryable transport failures.
Fetcher = Callable[[str], Awaitable[FetchResult]]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class ScanFailure:
    """One company-scan that ultimately failed (after retries)."""
    provider: Provider
    company_slug: str
    url: str
    status: Optional[int]      # last HTTP status seen, None if all transport errors
    reason: str                # short tag: "timeout" / "http_404" / "max_retries" / "parse_error"
    attempts: int


@dataclass(frozen=True)
class ScanRun:
    """Aggregate of one full ``run_scan`` pass.

    ``new_postings`` is the deduped list ready to insert into
    ``job_scan_history`` (the caller does the upsert).
    """
    new_postings: tuple[JobPosting, ...]
    failures: tuple[ScanFailure, ...]
    plans_attempted: int


# ── Internal helpers ─────────────────────────────────────────────────


def _backoff_seconds(attempt: int) -> float:
    """attempt is 1-indexed: 1 → 1s, 2 → 2s, 3 → 4s, capped at MAX."""
    if attempt < 1:
        return 0.0
    delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    return min(delay, _BACKOFF_MAX_SECONDS)


def _is_retryable_status(status: int) -> bool:
    """429 and any 5xx are retryable; everything else is terminal."""
    return status == 429 or 500 <= status < 600


async def _fetch_with_retry(
    plan: FetchPlan,
    fetcher: Fetcher,
    sleep: Sleeper,
) -> tuple[Optional[FetchResult], Optional[ScanFailure]]:
    """Fetch one plan, retrying on transient errors with exp backoff.

    Returns ``(result, None)`` on success (status==200) or
    ``(None, failure)`` on permanent failure.  Either tuple element
    is always None — they are mutually exclusive.
    """
    last_status: Optional[int] = None
    last_reason: str = "unknown"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = await fetcher(plan.url)
        except FetchError as exc:
            last_status = None
            last_reason = "transport_error"
            logger.info(
                "portal_scanner_worker: fetch raised on %s/%s attempt=%d err=%s",
                plan.provider, plan.company_slug, attempt, str(exc)[:200],
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            last_status = None
            last_reason = "fetcher_bug"
            logger.warning(
                "portal_scanner_worker: fetcher raised non-FetchError on %s/%s: %s",
                plan.provider, plan.company_slug, exc,
            )
        else:
            last_status = result.status
            if result.status == 200 and result.payload is not None:
                return result, None
            if not _is_retryable_status(result.status):
                # Permanent failure — don't burn retries.
                return None, ScanFailure(
                    provider=plan.provider,
                    company_slug=plan.company_slug,
                    url=plan.url,
                    status=result.status,
                    reason=f"http_{result.status}",
                    attempts=attempt,
                )
            last_reason = f"http_{result.status}"

        # Sleep before the next attempt unless this was the last try.
        if attempt < _MAX_RETRIES:
            await sleep(_backoff_seconds(attempt))

    return None, ScanFailure(
        provider=plan.provider,
        company_slug=plan.company_slug,
        url=plan.url,
        status=last_status,
        reason="max_retries" if last_status is not None else last_reason,
        attempts=_MAX_RETRIES,
    )


async def _scan_one(
    plan: FetchPlan,
    fetcher: Fetcher,
    sleep: Sleeper,
    provider_sem: asyncio.Semaphore,
    global_sem: asyncio.Semaphore,
) -> tuple[list[JobPosting], Optional[ScanFailure]]:
    """End-to-end scan of a single FetchPlan under both semaphores."""
    async with global_sem, provider_sem:
        result, failure = await _fetch_with_retry(plan, fetcher, sleep)
        if failure is not None or result is None:
            return [], failure
        try:
            postings = parse_payload(plan.provider, result.payload, plan.company_slug)
        except Exception as exc:
            logger.warning(
                "portal_scanner_worker: parse_payload raised on %s/%s: %s",
                plan.provider, plan.company_slug, exc,
            )
            return [], ScanFailure(
                provider=plan.provider,
                company_slug=plan.company_slug,
                url=plan.url,
                status=result.status,
                reason="parse_error",
                attempts=1,
            )
        return postings, None


def _build_provider_semaphores(
    overrides: Optional[Mapping[Provider, int]] = None,
) -> dict[Provider, asyncio.Semaphore]:
    """Build per-provider semaphores; overrides win over defaults."""
    out: dict[Provider, asyncio.Semaphore] = {}
    for provider, limit in _PROVIDER_CONCURRENCY.items():
        chosen = limit
        if overrides and provider in overrides:
            chosen = max(1, int(overrides[provider]))
        out[provider] = asyncio.Semaphore(chosen)
    return out


# ── Public entry ─────────────────────────────────────────────────────


async def run_scan(
    companies: Sequence[TrackedCompany],
    *,
    fetcher: Fetcher,
    seen_url_canonicals: Optional[Sequence[str]] = None,
    sleep: Sleeper = asyncio.sleep,
    provider_concurrency: Optional[Mapping[Provider, int]] = None,
    global_concurrency: int = _GLOBAL_CONCURRENCY,
) -> ScanRun:
    """Scan every tracked company and return new postings + failures.

    Parameters
    ----------
    companies:
        Tracked-company rows (already filtered by the caller for
        ``is_active``).  Empty input returns an empty ``ScanRun``.
    fetcher:
        Async callable that performs one HTTP GET and returns a
        ``FetchResult``.  May raise ``FetchError`` for transport
        failures the worker should retry.
    seen_url_canonicals:
        Optional set of canonical URLs already in scan history;
        matching new postings are dropped before the result is
        returned.  Pass ``None`` (or empty) to skip dedup.
    sleep:
        Awaitable sleep used between retry attempts.  Tests inject
        ``AsyncMock`` to make backoff instantaneous.
    provider_concurrency / global_concurrency:
        Knobs for the in-flight caps; defaults are conservative.
    """
    plans = plan_fetches(companies)
    if not plans:
        return ScanRun(new_postings=(), failures=(), plans_attempted=0)

    provider_sems = _build_provider_semaphores(provider_concurrency)
    global_sem = asyncio.Semaphore(max(1, int(global_concurrency)))

    async def _runner(plan: FetchPlan) -> tuple[list[JobPosting], Optional[ScanFailure]]:
        sem = provider_sems.get(plan.provider)
        if sem is None:
            # Unknown provider — should not happen because plan_fetches
            # already filters, but defend in case of future provider drift.
            return [], ScanFailure(
                provider=plan.provider,
                company_slug=plan.company_slug,
                url=plan.url,
                status=None,
                reason="unknown_provider",
                attempts=0,
            )
        return await _scan_one(plan, fetcher, sleep, sem, global_sem)

    results = await asyncio.gather(
        *(_runner(p) for p in plans),
        return_exceptions=False,
    )

    all_postings: list[JobPosting] = []
    failures: list[ScanFailure] = []
    for postings, failure in results:
        all_postings.extend(postings)
        if failure is not None:
            failures.append(failure)

    new_postings = filter_new_postings(
        all_postings,
        seen_url_canonicals=seen_url_canonicals or (),
    )

    return ScanRun(
        new_postings=tuple(new_postings),
        failures=tuple(failures),
        plans_attempted=len(plans),
    )


__all__ = [
    "FetchError", "FetchResult", "Fetcher", "Sleeper",
    "ScanFailure", "ScanRun",
    "run_scan",
]
