"""B0.persist.core — pure-fn row builders for batch persistence.

Composes a ``ScoringResult`` (from B0.scorer) into the JSONB-heavy
shape that ``public.applications`` expects, without touching any
database client.  Keeping this layer pure means:

* Tests stay AI-free and DB-free (no Supabase, no service-role key).
* Re-running ``build_application_row`` for the same input always
  produces the same output (idempotency hash for dedup is included).
* The thin async persister (next slice) becomes a 5-line wrapper
  around ``db.insert(rows)``.

Schema rationale (no migration in this slice):
    The applications table doesn't have dedicated ``posting_url``
    or ``fit_score`` columns yet.  We park batch-discovery metadata
    in ``confirmed_facts`` (JSONB) and the score in ``scores``
    (JSONB).  Both fields already exist and both are user-scoped
    behind RLS via ``user_id``.  When B0.persist.schema lands, we
    can pull these out into typed columns; the JSONB hedge means
    older rows stay readable.

Hard rules:
    - status='draft' so the row shows up in the user's Drafts pane,
      NOT the active pipeline (the user has to hit Generate per row
      to opt into running modules — keeps batch import cheap).
    - title falls back through (ScoringResult.title → company →
      "Untitled — <short-canonical>") so the Drafts list is never
      empty/nameless.
    - dedup_key is sha256(user_id + canonical_url)[:32]; same user
      pasting the same URL twice in two batches collapses to one
      row at the route layer (B0.persist.route).
    - We NEVER persist BatchEntry from the failed/below-threshold
      buckets — only ranked.  Below-threshold rows could be stored
      with a tag, but adding that complexity now risks polluting
      Drafts with low-fit noise; keep it ranked-only.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from app.services.batch_evaluator import RankedBatch, ScoringResult

# Default status for batch-imported rows.  See "Hard rules" above.
DEFAULT_STATUS = "draft"

# How many chars of the canonical URL we splice into the fallback
# title.  Long enough to disambiguate, short enough not to wrap.
_TITLE_URL_HINT_LEN = 48


def _short_url_hint(canonical_url: str) -> str:
    """Last URL segment for the fallback title.

    For "https://boards.greenhouse.io/acme/jobs/12345" → "12345".
    For URLs without a meaningful tail, fall back to the host.
    """
    if not canonical_url:
        return "(no url)"
    try:
        parsed = urlparse(canonical_url)
        # Prefer last non-empty path segment.
        segments = [s for s in parsed.path.split("/") if s]
        if segments:
            tail = segments[-1]
            if len(tail) > _TITLE_URL_HINT_LEN:
                tail = tail[:_TITLE_URL_HINT_LEN] + "…"
            return tail
        return parsed.netloc or canonical_url[:_TITLE_URL_HINT_LEN]
    except Exception:
        return canonical_url[:_TITLE_URL_HINT_LEN]


def _resolve_title(result: ScoringResult) -> str:
    """ScoringResult.title → company → fallback derived from URL."""
    t = (result.title or "").strip()
    if t:
        return t
    c = (result.company or "").strip()
    if c:
        return c
    return f"Untitled — {_short_url_hint(result.canonical_url)}"


def make_dedup_key(*, user_id: str, canonical_url: str) -> str:
    """sha256(user_id + canonical_url)[:32].

    Used at the route layer to avoid double-inserting when a user
    re-runs the same batch.  Hash domain is per-user so the same
    URL across two users never collides.
    """
    payload = f"{user_id}\x1f{canonical_url}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def build_application_row(
    *,
    result: ScoringResult,
    user_id: str,
    batch_id: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compose one application row from a ScoringResult.

    Output is a JSON-safe dict ready to hand to a Supabase insert.
    Every JSONB column gets a fully populated nested dict so the row
    round-trips cleanly through the existing ``modules`` defaults
    in the table DDL.

    Caller's responsibility:
    * Pass only ranked results (not below_threshold or failed).
    * Generate a single ``batch_id`` per route call so all rows
      from one paste share a grouping key.
    * Skip persistence entirely if ``result.error`` is set — we
      assert this defensively but don't raise (we just emit a row
      with a tagged scores block so the bug is visible in DB).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    iso_now = now.isoformat()

    title = _resolve_title(result)
    dedup_key = make_dedup_key(
        user_id=user_id, canonical_url=result.canonical_url
    )

    confirmed_facts: Dict[str, Any] = {
        "source": "batch",
        "batch_id": batch_id,
        "canonical_url": result.canonical_url,
        "dedup_key": dedup_key,
        "company": (result.company or "").strip() or None,
        "title": (result.title or "").strip() or None,
        "imported_at": iso_now,
    }

    scores: Dict[str, Any] = {
        "fit": result.fit_score,
        "source": "batch_scorer",
        "scored_at": iso_now,
    }
    if result.error:  # defensive — caller should have filtered.
        scores["error"] = result.error

    return {
        "user_id": user_id,
        "title": title,
        "status": DEFAULT_STATUS,
        "confirmed_facts": confirmed_facts,
        "scores": scores,
    }


def build_application_rows(
    *,
    ranked: RankedBatch,
    user_id: str,
    batch_id: str,
    now: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], ...]:
    """Build rows for every entry in ``ranked.ranked`` (only).

    Excludes ``below_threshold`` and ``failed`` deliberately — see
    module docstring.  Returns a tuple to make the result hashable
    for cache wrappers and to discourage in-place mutation.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return tuple(
        build_application_row(
            result=r, user_id=user_id, batch_id=batch_id, now=now
        )
        for r in ranked.ranked
    )


__all__ = [
    "DEFAULT_STATUS",
    "build_application_row",
    "build_application_rows",
    "make_dedup_key",
]
