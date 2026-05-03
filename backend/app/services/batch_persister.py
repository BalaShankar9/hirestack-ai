"""B0.persist — thin async wrapper around the pure-fn row builder.

Splits the pure-fn ``batch_persister_core`` (no I/O) from the I/O-bound
"actually write to Supabase" step.  Tests for this file mock the
``Database`` Protocol directly; tests for the row-shape live in
``test_batch_persister_core``.

Why two files:
    The route slice (``batch_generate.commit_route``) imports
    ``persist_ranked_batch`` and never sees the row dict directly.
    The pure-fn shape lives in ``batch_persister_core`` so other
    callers (CLI, MCP server) can build rows without dragging the
    Supabase client into their import graph.

Idempotency (B0.persist.idempotency):
    Before inserting, we query existing applications for this user
    that already carry one of the candidate ``dedup_key`` values.
    Matches are SKIPPED (not re-inserted) and surfaced in the
    return value so the route can tell the UI "3 inserted, 2
    already in your Drafts".  The DB index
    ``applications_batch_dedup_uniq`` (migration 20260506) is the
    last-line defence against a race — two concurrent commit
    requests could both pre-query before either inserts; whichever
    inserts second sees IntegrityError, which we re-raise.

Hard rules:
    - Empty ``ranked.ranked`` is a no-op — returns empty result, no
      DB calls.  Saves the no-op insert/query that would otherwise
      spam the Supabase rate limit when a user pastes 25 URLs and
      none cross the threshold.
    - Insertion is sequential (not gathered) so a partial-failure
      mid-batch leaves the prior rows committed and surfaces the
      Exception to the caller, who logs it.  Gather-with-cancel
      could leave torn state in failure cases.
    - Pre-query is the *only* dedup mechanism we trust for clean
      UX; the unique index is a safety net.  If a row is in
      ``existing_keys`` we never call ``db.create`` for it.
    - Return value is a frozen dataclass for hashability.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple

from app.core.database import TABLES
from app.services.batch_evaluator import RankedBatch
from app.services.batch_persister_core import build_application_rows

logger = logging.getLogger(__name__)


class _DBLike(Protocol):
    """Minimal DB surface we need.  Mirrors ``app.core.database.Database``."""
    async def create(
        self,
        table: str,
        data: dict,
        doc_id: Optional[str] = None,
    ) -> str: ...

    async def query(
        self,
        table: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        order_direction: str = "DESCENDING",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]: ...


@dataclass(frozen=True)
class PersistResult:
    """Outcome of a ``persist_ranked_batch`` call.

    inserted: tuple of (canonical_url, new_application_id) for rows
        actually written this call.
    skipped:  tuple of (canonical_url, existing_application_id) for
        rows that already had the same dedup_key for this user.
    """
    inserted: Tuple[Tuple[str, str], ...]
    skipped: Tuple[Tuple[str, str], ...]

    @property
    def inserted_count(self) -> int:
        return len(self.inserted)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def make_batch_id() -> str:
    """Generate a fresh batch id.

    32-char hex (uuid4 without hyphens) so it round-trips cleanly
    through JSONB and URL-encodes without escapes.  Caller may
    override by passing ``batch_id=`` to ``persist_ranked_batch``.
    """
    return uuid.uuid4().hex


async def _existing_dedup_keys(
    *, db: _DBLike, user_id: str, candidate_keys: List[str],
) -> Dict[str, str]:
    """Return {dedup_key: application_id} for rows already in DB.

    Filters to ``user_id`` first (RLS-aligned + uses the per-user
    btree index from migration 20260428010000) then post-filters
    on the JSONB key in Python.  We don't push the JSONB filter
    into Supabase because the abstract ``query`` Protocol doesn't
    expose JSONB operators — keeping the surface small.

    For batches up to MAX_URLS=25 the post-filter is trivially
    cheap; we already cap candidate_keys at 25 keys.  If a user
    has thousands of applications, this still does *one* round-trip
    and an in-memory dict scan.
    """
    if not candidate_keys:
        return {}
    # We need confirmed_facts + id; query() returns full rows so
    # everything we need is there.  RLS + user_id filter scopes the
    # result to this user's rows only.
    rows = await db.query(
        TABLES["applications"],
        filters=[("user_id", "==", user_id)],
    )
    out: Dict[str, str] = {}
    candidate_set = set(candidate_keys)
    for row in rows or []:
        cf = row.get("confirmed_facts") or {}
        if not isinstance(cf, dict):
            continue
        key = cf.get("dedup_key")
        if isinstance(key, str) and key in candidate_set:
            row_id = row.get("id")
            if row_id is not None:
                out[key] = str(row_id)
    return out


async def persist_ranked_batch(
    *,
    db: _DBLike,
    ranked: RankedBatch,
    user_id: str,
    batch_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> PersistResult:
    """Insert ``ranked.ranked`` entries that don't already exist for this user.

    Returns a ``PersistResult`` with ``inserted`` and ``skipped``
    pairs in input order.  ``below_threshold`` and ``failed``
    buckets are NEVER persisted — enforced in the pure-fn builder
    and retested at this I/O boundary.

    Args:
        db: Database surface (any object satisfying ``_DBLike``).
        ranked: Output of ``rank_batch``.
        user_id: Authenticated caller.  Stored on every row.
        batch_id: Optional caller-supplied id.  Defaults to a fresh
            uuid4 hex.  Useful for tests + idempotent retries.
        now: Optional fixed timestamp.  Defaults to ``datetime.now(UTC)``
            inside the row builder.

    Raises:
        Whatever ``db.create`` or ``db.query`` raises — we don't
        swallow.  Caller (the route) logs and returns 5xx so the
        user can retry.  IntegrityError from the unique index is
        the rare race condition; log it and let it bubble.
    """
    if not ranked.ranked:
        return PersistResult(inserted=tuple(), skipped=tuple())

    if batch_id is None:
        batch_id = make_batch_id()

    rows = build_application_rows(
        ranked=ranked,
        user_id=user_id,
        batch_id=batch_id,
        now=now,
    )

    candidate_keys = [r["confirmed_facts"]["dedup_key"] for r in rows]
    existing = await _existing_dedup_keys(
        db=db, user_id=user_id, candidate_keys=candidate_keys,
    )

    table = TABLES["applications"]
    inserted: List[Tuple[str, str]] = []
    skipped: List[Tuple[str, str]] = []

    for row in rows:
        url = row["confirmed_facts"]["canonical_url"]
        key = row["confirmed_facts"]["dedup_key"]
        if key in existing:
            skipped.append((url, existing[key]))
            logger.info(
                "batch_persist_skipped user=%s batch=%s existing=%s url=%s",
                user_id, batch_id, existing[key], url,
            )
            continue
        app_id = await db.create(table, dict(row))
        inserted.append((url, app_id))
        logger.info(
            "batch_persist_inserted user=%s batch=%s app=%s url=%s",
            user_id, batch_id, app_id, url,
        )

    return PersistResult(inserted=tuple(inserted), skipped=tuple(skipped))


__all__ = [
    "PersistResult",
    "make_batch_id",
    "persist_ranked_batch",
]
