"""A2.api — /api/insights route.

Wraps the pure-fn cores ``pattern_insights`` (A2.a) and
``insights_blockers`` (A2.b) into a single authenticated endpoint that
hydrates ``ApplicationRecord`` objects from the user's ``applications``
rows and returns a JSON-serializable insights bundle for the
``/dashboard/insights`` page (frontend slice ships separately).

Why one endpoint, not two:
    Both cores read the same underlying rows; one query → one render
    keeps the UI atomic and avoids N+1 round-trips. The response is
    namespaced (``patterns`` / ``blockers`` / ``recommendations``) so
    the frontend can mount each panel independently.

Hydration rules (tolerant of schema drift):
    - ``status`` is forwarded raw; the cores call
      ``canonicalize_for_analytics`` themselves.
    - ``fit_score`` is read from ``scores.overall`` (0-100 in DB) and
      rescaled to the 0-5 surface the cores expect. Missing → ``None``.
    - ``archetype_label`` and ``rejection_reason`` are read from the
      row if present, otherwise ``None``. Both core sections gracefully
      degrade to ``InsufficientData`` in that case.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.core.database import TABLES, get_db
from app.core.security import limiter
from app.services.insights_blockers import (
    BlockerReport,
    RejectedApplication,
    build_recommendations,
    classify_blockers,
)
from app.services.pattern_insights import (
    ApplicationRecord,
    InsufficientData,
    PatternInsights,
    compute_pattern_insights,
)

router = APIRouter()

# Hard cap on the per-user query — insights stop being interesting past
# a few hundred apps and unbounded SELECT is a footgun.
_MAX_APPLICATIONS = 500

# DB stores fit on a 0-100 scale; cores expect 0-5.
_DB_TO_CORE_SCORE = 5.0 / 100.0


# ── Hydration helpers ────────────────────────────────────────────────


def _coerce_fit_score(scores: Any) -> Optional[float]:
    """Pull ``scores.overall`` and rescale to 0-5; return None on missing."""
    if not isinstance(scores, dict):
        return None
    overall = scores.get("overall")
    if not isinstance(overall, (int, float)):
        return None
    rescaled = float(overall) * _DB_TO_CORE_SCORE
    # Clamp defensively; bad data shouldn't poison the bucketing.
    if rescaled < 0.0:
        return 0.0
    if rescaled > 5.0:
        return 5.0
    return rescaled


def _coerce_optional_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def hydrate_records(
    rows: List[Dict[str, Any]],
) -> tuple[List[ApplicationRecord], List[RejectedApplication]]:
    """Split DB rows into the two core inputs.

    Pure & exported for unit tests — no DB access.
    """
    pattern_records: List[ApplicationRecord] = []
    blocker_records: List[RejectedApplication] = []

    for row in rows:
        app_id = str(row.get("id") or row.get("application_id") or "")
        if not app_id:
            continue
        status = str(row.get("status") or "").strip()
        if not status:
            continue

        pattern_records.append(ApplicationRecord(
            application_id=app_id,
            status=status,
            fit_score=_coerce_fit_score(row.get("scores")),
            archetype_label=_coerce_optional_str(row.get("archetype_label")),
        ))
        blocker_records.append(RejectedApplication(
            application_id=app_id,
            status=status,
            rejection_reason=_coerce_optional_str(row.get("rejection_reason")),
        ))

    return pattern_records, blocker_records


# ── Serializers (frozen dataclass → JSON-safe dict) ──────────────────


def _serialize(value: Any) -> Any:
    """Recursive frozen-dataclass → dict converter.

    Tolerates tuples (→ lists), nested dataclasses, and the
    ``InsufficientData`` sentinel (kept whole so the frontend can
    branch on its presence).
    """
    if value is None:
        return None
    if isinstance(value, InsufficientData):
        # Tag the dict so the UI can pattern-match on `kind`.
        return {"kind": "insufficient_data", **asdict(value)}
    if is_dataclass(value):
        # Replace each field through _serialize so nested tuples / dataclasses
        # are converted too.
        out: Dict[str, Any] = {}
        for k, v in asdict(value).items():
            # asdict already recurses, but it leaves tuples as-is and
            # InsufficientData as nested dict (losing our `kind` tag) —
            # so re-walk via the live attribute, not the asdict copy.
            out[k] = _serialize(getattr(value, k))
        return out
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def serialize_pattern_insights(insights: PatternInsights) -> Dict[str, Any]:
    return _serialize(insights)


def serialize_blocker_report(report: BlockerReport) -> Dict[str, Any]:
    return _serialize(report)


# ── Route ────────────────────────────────────────────────────────────


@router.get("/insights")
@limiter.limit("30/minute")
async def get_insights(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the full insights bundle for ``/dashboard/insights``.

    Response shape::

        {
          "patterns": <PatternInsights>,
          "blockers": <BlockerReport>,
          "recommendations": [<Recommendation>, ...],
          "total_applications": int
        }
    """
    db = get_db()
    rows = await db.query(
        TABLES["applications"],
        filters=[("user_id", "==", current_user["id"])],
        limit=_MAX_APPLICATIONS,
    )

    pattern_records, blocker_records = hydrate_records(rows or [])

    insights = compute_pattern_insights(pattern_records)
    blockers = classify_blockers(blocker_records)
    recommendations = build_recommendations(insights, blockers)

    return {
        "patterns": serialize_pattern_insights(insights),
        "blockers": serialize_blocker_report(blockers),
        "recommendations": [_serialize(r) for r in recommendations],
        "total_applications": len(pattern_records),
    }


__all__ = [
    "router",
    "hydrate_records",
    "serialize_pattern_insights",
    "serialize_blocker_report",
]
