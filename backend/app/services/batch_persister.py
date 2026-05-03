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

Hard rules:
    - Empty ``ranked.ranked`` is a no-op — returns empty tuple, no
      DB calls.  Saves the no-op insert that would otherwise spam
      the Supabase rate limit when a user pastes 25 URLs and none
      cross the threshold.
    - Insertion is sequential (not gathered) so a partial-failure
      mid-batch leaves the prior rows committed and surfaces the
      Exception to the caller, who logs it.  Gather-with-cancel
      could leave torn state in failure cases.
    - We do NOT enforce DB-level idempotency in this slice.  The
      ``dedup_key`` is stored in ``confirmed_facts`` JSONB so a
      future migration can add a partial unique index; same-paste
      twice today produces two rows.  Documented in commit msg.
    - Return value is a tuple of (canonical_url, application_id)
      pairs in input order.  Tuple (not list) for hashability.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional, Protocol, Tuple

from app.core.database import TABLES
from app.services.batch_evaluator import RankedBatch
from app.services.batch_persister_core import build_application_rows

logger = logging.getLogger(__name__)


class _DBLike(Protocol):
    """Minimal DB surface we need.  Mirrors ``app.core.database.Database.create``."""
    async def create(
        self,
        table: str,
        data: dict,
        doc_id: Optional[str] = None,
    ) -> str: ...


def make_batch_id() -> str:
    """Generate a fresh batch id.

    32-char hex (uuid4 without hyphens) so it round-trips cleanly
    through JSONB and URL-encodes without escapes.  Caller may
    override by passing ``batch_id=`` to ``persist_ranked_batch``.
    """
    return uuid.uuid4().hex


async def persist_ranked_batch(
    *,
    db: _DBLike,
    ranked: RankedBatch,
    user_id: str,
    batch_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[Tuple[str, str], ...]:
    """Insert all ``ranked.ranked`` entries into ``applications``.

    Returns a tuple of ``(canonical_url, application_id)`` pairs in
    input order.  ``below_threshold`` and ``failed`` buckets are
    NEVER persisted — that decision lives in the pure-fn builder
    and is enforced by ``test_batch_persister_core``.

    Args:
        db: Database surface (any object with ``async create(table, data) -> id``).
        ranked: Output of ``rank_batch``.
        user_id: Authenticated caller.  Stored on every row.
        batch_id: Optional caller-supplied id.  Defaults to a fresh
            uuid4 hex.  Useful for tests + idempotent retries.
        now: Optional fixed timestamp.  Defaults to ``datetime.now(UTC)``
            inside the row builder.

    Raises:
        Whatever ``db.create`` raises — we don't swallow.  Caller
        (the route) is expected to log + return 5xx so the user can
        retry.
    """
    if not ranked.ranked:
        return tuple()

    if batch_id is None:
        batch_id = make_batch_id()

    rows = build_application_rows(
        ranked=ranked,
        user_id=user_id,
        batch_id=batch_id,
        now=now,
    )

    out = []
    table = TABLES["applications"]
    for row in rows:
        app_id = await db.create(table, dict(row))
        out.append((row["confirmed_facts"]["canonical_url"], app_id))
        logger.info(
            "batch_persist_inserted user=%s batch=%s app=%s url=%s",
            user_id, batch_id, app_id,
            row["confirmed_facts"]["canonical_url"],
        )
    return tuple(out)


__all__ = [
    "make_batch_id",
    "persist_ranked_batch",
]
