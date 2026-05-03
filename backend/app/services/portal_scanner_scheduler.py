"""B1.next.cron — scheduler tick orchestrator.

One cron-callable entrypoint that runs a complete scan tick for one
user: load the watchlist, fan out to ``portal_scanner_worker.run_scan``,
mark the rows as scanned (whether the scans succeeded or failed —
``last_scanned_at`` means "we attempted", which is what the next
tick's "stalest first" ordering needs).

Deployment-agnostic on purpose
-------------------------------
Pinning a deployment story (Railway worker? FastAPI BackgroundTasks?
external cron hitting a protected endpoint?) is a separate decision.
This module is just an async function — wrap it however the
infrastructure dictates without touching the orchestration logic.

What's NOT here
---------------
* Persisting ``new_postings`` to scan history — the schema for that
  is unstaged WIP (see B1.next.repo for context).  When it lands
  we'll add an ``insert_new_postings`` helper to repo and call it
  here right after ``run_scan`` returns.
* Multi-user batching / fairness queueing — caller picks one user.
* Notification emission (email digest of new postings) — that's a
  consumer downstream of the scan-history table, not part of the
  tick itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.services.portal_scanner_worker import Fetcher, ScanRun, run_scan
from app.services.tracked_companies_repo import (
    _RepoDB,
    load_watchlist_for_user,
    mark_scanned,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickResult:
    """Aggregate of one ``run_user_scan_tick`` invocation.

    Fields
    ------
    scanned_count:
        How many tracked-companies rows were attempted in this tick
        (== number of WatchlistEntries loaded).
    plans_attempted:
        From ``ScanRun.plans_attempted`` — equal to ``scanned_count``
        in the happy path; lower if ``portal_scanner.plan_fetches``
        dropped any companies (e.g. unknown future provider that
        sneaks past repo's filter).
    new_postings_count:
        How many *new* postings the worker returned (after dedup
        against ``seen_url_canonicals`` if/when wired in).  Zero
        is a valid healthy result — ATSes don't post every minute.
    failure_count:
        From ``ScanRun.failures`` — companies whose scan ultimately
        failed after retries.  A high failure_count without
        scanned_count moving up tick-over-tick is the signal that
        a provider is degraded.
    marked_scanned_count:
        How many ``last_scanned_at`` updates landed.  Should equal
        ``scanned_count`` unless a row was deleted between the
        load and the mark (silent zero-contribution from
        ``mark_scanned`` — see B1.next.repo).
    """

    scanned_count: int
    plans_attempted: int
    new_postings_count: int
    failure_count: int
    marked_scanned_count: int


async def run_user_scan_tick(
    user_id: str,
    *,
    db: _RepoDB,
    fetcher: Fetcher,
    now: Optional[datetime] = None,
) -> TickResult:
    """Run one scheduler tick for one user.

    Parameters
    ----------
    user_id:
        The user whose watchlist to scan.  RLS in production restricts
        DB rows to this user; in tests the fake DB filters in Python.
    db:
        DB handle satisfying ``_RepoDB`` (query + update).  In
        production this is the SupabaseDB singleton; tests inject a
        fake.
    fetcher:
        Production callers pass ``portal_scanner_http.make_httpx_fetcher()``;
        tests pass an in-memory async fn that returns canned
        ``FetchResult`` payloads.
    now:
        Override for the tick's "scanned at" timestamp.  Default is
        ``datetime.now(timezone.utc)``; tests pin to a fixed value
        for assertion stability.

    Empty-watchlist short-circuit
    -----------------------------
    If the user has no enabled companies, we return immediately
    without invoking ``run_scan`` or ``mark_scanned`` — no work,
    no DB chatter, no spurious "tick attempted 0" log noise.

    Mark-after-scan, not before
    ---------------------------
    We update ``last_scanned_at`` *after* ``run_scan`` returns so
    a crash mid-scan doesn't poison the next tick's ordering.
    The trade-off: if the scheduler is hung mid-scan, a parallel
    invocation could double-scan.  But this orchestrator is
    expected to be invoked from cron at minute granularity, and
    ``run_scan`` finishes in seconds; double-invocation is
    operator error, and the worker's own retries make it idempotent
    on the read side.

    Mark-on-failure-too
    -------------------
    A failed scan still bumps ``last_scanned_at``.  If we only
    marked successes, a broken provider would keep pushing the
    same dead companies to the front of the "stalest first" queue,
    crowding out healthy companies.  Marking-on-attempt gives
    every company a fair share of ticks.
    """
    entries = await load_watchlist_for_user(user_id, db)
    if not entries:
        return TickResult(
            scanned_count=0,
            plans_attempted=0,
            new_postings_count=0,
            failure_count=0,
            marked_scanned_count=0,
        )

    companies = tuple(e.company for e in entries)
    scan_run: ScanRun = await run_scan(companies, fetcher=fetcher)

    scanned_at = now or datetime.now(timezone.utc)
    marked = await mark_scanned(
        db,
        (e.id for e in entries),
        scanned_at=scanned_at,
    )

    return TickResult(
        scanned_count=len(entries),
        plans_attempted=scan_run.plans_attempted,
        new_postings_count=len(scan_run.new_postings),
        failure_count=len(scan_run.failures),
        marked_scanned_count=marked,
    )


__all__ = ["TickResult", "run_user_scan_tick"]
