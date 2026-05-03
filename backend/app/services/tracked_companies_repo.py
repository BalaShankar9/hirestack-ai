"""DB helpers for the portal scanner scheduler.

The pure-fn worker (services/portal_scanner_worker.py) and the
production Fetcher (services/portal_scanner_http.py) handle the scan
itself.  This module owns the **persistence boundary** — what to
scan next, and how to mark a company as freshly scanned.

What's here
-----------
* ``load_enabled_for_user(user_id, db)`` → list[TrackedCompany]
  Loads every ``tracked_companies`` row where ``enabled = true`` for
  the user, ordered "stalest first" (rows that have **never** been
  scanned come first, then ascending by ``last_scanned_at``).  This
  matches the partial index from migration ``20260507000000``:
  ``(user_id, last_scanned_at NULLS FIRST) WHERE enabled``.

* ``mark_scanned(db, ids, *, scanned_at)`` → int
  Sets ``last_scanned_at`` on every row in ``ids``.  Returns the
  number of rows updated.  Used by the scheduler after each scan
  run completes so the next iteration picks the next stalest batch.

What's NOT here (intentionally deferred)
----------------------------------------
* Persisting ``new_postings`` to ``job_scan_history`` — that table's
  schema lives in an unstaged WIP migration.  We'll add the
  postings-persist helper when that schema lands cleanly on main.
* Cron / scheduler glue — composes load_enabled_for_user + run_scan
  + mark_scanned and lives one layer up; depends on a deployment
  story (Railway worker? FastAPI background task? cron-only?) that
  isn't pinned yet.
* Cross-user batching — for now the scheduler caller picks one user
  and scans all their companies.  Multi-tenant fairness queueing
  is a future concern.

Why a repo module instead of a service class
--------------------------------------------
Two pure async functions with explicit ``db`` injection match the
pattern set by ``batch_persister.py`` (B0.persist.route, c3ac9dc):
no class, no singleton, no hidden state — caller passes the DB
they want, and tests pass a fake.  Avoids the lifecycle questions
that come with a service class (when to instantiate, when to share).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Protocol, Sequence

from app.core.database import TABLES
from app.services.portal_scanner import PROVIDERS, TrackedCompany


@dataclass(frozen=True)
class WatchlistEntry:
    """A tracked-companies row paired with its DB row id.

    The scheduler tick (B1.next.cron) needs both: ``company`` to
    drive ``portal_scanner_worker.run_scan``, and ``id`` to feed
    back into ``mark_scanned`` when the scan completes.  We keep
    them in one frozen object so the two never get out of sync
    in the orchestrator.
    """

    id: str
    company: TrackedCompany


# ── DB Protocol (only the methods we actually use) ───────────────────


class _RepoDB(Protocol):
    async def query(
        self,
        table: str,
        filters: list[tuple] | None = ...,
        order_by: str | None = ...,
        order_direction: str = ...,
        limit: int | None = ...,
        offset: int | None = ...,
    ) -> List[Mapping[str, Any]]: ...

    async def update(
        self, table: str, doc_id: str, data: dict[str, Any]
    ) -> bool: ...


# ── Row → dataclass mapping ──────────────────────────────────────────


def _row_to_tracked_company(row: Mapping[str, Any]) -> TrackedCompany:
    """Translate a DB row into the worker's frozen TrackedCompany.

    The schema (B2.schema, 63456da) was deliberately built with field
    names matching the dataclass — provider / company_slug /
    workday_tenant — so this is a one-line dict-to-kwargs unpack
    with explicit field selection.  Explicit selection means a
    schema drift (e.g. column rename) surfaces here, not deep in
    the worker.
    """
    return TrackedCompany(
        provider=row["provider"],
        company_slug=row["company_slug"],
        workday_tenant=row.get("workday_tenant"),
    )


# ── load_enabled_for_user ────────────────────────────────────────────


def _stalest_first_key(row: Mapping[str, Any]) -> tuple[bool, str]:
    """Sort key: (has_been_scanned, scan_timestamp).

    Tuples sort lexicographically, so ``False`` (never scanned)
    sorts before ``True`` (scanned at some point), which is what
    we want.  Within the scanned bucket, oldest timestamp wins.
    """
    last = row.get("last_scanned_at")
    if last is None:
        return (False, "")
    # last_scanned_at is stored as ISO-8601 (Supabase TIMESTAMPTZ
    # serializes that way), so plain string compare matches
    # chronological order without a parse cost.
    return (True, str(last))


async def load_enabled_for_user(
    user_id: str,
    db: _RepoDB,
) -> List[TrackedCompany]:
    """Return every enabled tracked company for a user, stalest first.

    Scheduler usage::

        companies = await load_enabled_for_user(user.id, db)
        result = await run_scan(companies, fetcher=make_httpx_fetcher())
        await mark_scanned(db, [c.id for c in companies], scanned_at=now())

    Defensive notes
    ---------------
    * Rows with an unknown ``provider`` (shouldn't happen — the DB
      CHECK enforces ``PROVIDERS``, and B2.core mirrors it — but a
      future provider added to the dataclass before the migration
      ships could trip this) are dropped, not raised.  The next
      scheduler tick still runs for the rest of the watchlist.
    * Disabled rows are filtered server-side via the ``enabled = True``
      filter; we don't trust the caller to pre-filter.
    * Empty user → empty list, no DB error.
    """
    rows = await db.query(
        TABLES["tracked_companies"],
        filters=[
            ("user_id", "==", user_id),
            ("enabled", "==", True),
        ],
        # We post-sort in Python because Supabase doesn't expose
        # NULLS FIRST through the DB layer (see core/database.py
        # query() — only desc bool is plumbed).  The partial index
        # from migration 20260507000000 still answers the WHERE,
        # which is the expensive part.
        order_by=None,
    )

    out: List[TrackedCompany] = []
    for row in sorted(rows, key=_stalest_first_key):
        provider = row.get("provider")
        if provider not in PROVIDERS:
            continue
        out.append(_row_to_tracked_company(row))
    return out


# ── load_watchlist_for_user ──────────────────────────────────────────


async def load_watchlist_for_user(
    user_id: str,
    db: _RepoDB,
) -> List[WatchlistEntry]:
    """Same query+ordering as ``load_enabled_for_user`` but keeps row ids.

    The scheduler tick uses this — it needs the ``id`` to call
    ``mark_scanned`` after the scan completes.  The pure-fn worker
    only takes ``TrackedCompany``, so we pair them in
    ``WatchlistEntry`` to keep the two in lockstep through the tick.

    Why a sister function instead of replacing ``load_enabled_for_user``?
    The simpler signature is cleaner for non-scheduler callers (e.g.
    a future "preview my watchlist" endpoint that doesn't need ids).
    Both walk the same ``db.query`` path — the cost difference is
    nil; the API surface gain is real.
    """
    rows = await db.query(
        TABLES["tracked_companies"],
        filters=[
            ("user_id", "==", user_id),
            ("enabled", "==", True),
        ],
        order_by=None,
    )

    out: List[WatchlistEntry] = []
    for row in sorted(rows, key=_stalest_first_key):
        provider = row.get("provider")
        if provider not in PROVIDERS:
            continue
        out.append(
            WatchlistEntry(
                id=row["id"],
                company=_row_to_tracked_company(row),
            )
        )
    return out


# ── mark_scanned ─────────────────────────────────────────────────────


async def mark_scanned(
    db: _RepoDB,
    ids: Iterable[str],
    *,
    scanned_at: datetime,
) -> int:
    """Set ``last_scanned_at = scanned_at`` for every row in ``ids``.

    Returns the count of rows successfully updated.  A row whose id
    does not exist (e.g. user deleted the watchlist entry between
    load and mark) silently contributes 0 to the count — the
    scheduler treats that as "this row is gone, fine, move on".

    Sequential (not gather) on purpose
    ----------------------------------
    Mirrors batch_persister.py's persist_ranked_batch: at scheduler
    cadence (one tick per minute at most), the latency win from
    parallel UPDATEs isn't worth the complexity.  A failure on row
    3 lets rows 1-2 stay marked and the caller can re-run the
    scheduler for the rest.

    Stable timestamp
    ----------------
    Caller passes one ``scanned_at`` for the entire batch so all rows
    from the same scan tick share the timestamp — useful for
    operator queries ("which rows did the 03:00 tick touch?").
    """
    table = TABLES["tracked_companies"]
    iso = _to_iso(scanned_at)
    update = {"last_scanned_at": iso}

    updated = 0
    for row_id in ids:
        ok = await db.update(table, row_id, update)
        if ok:
            updated += 1
    return updated


def _to_iso(ts: datetime) -> str:
    """Render a datetime as an ISO-8601 string Supabase accepts.

    Supabase stores TIMESTAMPTZ; isoformat() with a tz-aware
    datetime round-trips correctly.  A naive datetime is treated
    by Supabase as UTC, which is what we want for scheduler ticks
    that already run on UTC boxes — but we still warn the
    explicit-tz-aware caller is the safer pattern.
    """
    return ts.isoformat()


__all__ = [
    "WatchlistEntry",
    "load_enabled_for_user",
    "load_watchlist_for_user",
    "mark_scanned",
]
