"""B0.api — /api/generate/batch route.

Wraps the pure-fn ``batch_evaluator.plan_batch`` (and the result
serializer) into an authenticated endpoint that takes a list of
arbitrary job-posting URLs and returns a *validated, deduped,
canonicalized* plan plus the per-URL rejection reasons.

Why this slice stops at validation:
    The full B0 fan-out (parallel scoring against the user's
    profile + persistence into ``applications``) lives in the next
    slice (``batch_scorer_worker``).  Splitting validation off is
    intentional — ``plan_batch`` is fast (< 5ms) and pure, so the
    UI can paste a giant list, see "12 accepted / 3 rejected" with
    per-row reasons (over_cap / empty / invalid_url / duplicate)
    *before* committing to the slow AI fan-out.  This matches the
    "preview before commit" UX the journal calls out for the batch
    paste flow.

Hard rules:
    - ``MAX_URLS`` cap is enforced inside ``plan_batch``; we surface
      it via ``rejected[].reason == "over_cap"`` rather than 4xx so
      the user sees *which* URLs got cut.
    - This endpoint NEVER touches the AI router or the DB — it's
      pure validation.  No PII written, nothing to clean up on
      retry.  Idempotent: same input → same output.
    - 10/minute rate limit (lower than insights' 30/min): paste
      endpoints attract bots.  Tune up if needed; tune down hurts.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.security import limiter
from app.services.batch_evaluator import (
    MAX_URLS,
    MIN_FIT_SCORE_CEIL,
    MIN_FIT_SCORE_FLOOR,
    BatchPlan,
    plan_batch,
)

router = APIRouter()


# ── Request / Response models ────────────────────────────────────────


class BatchPlanRequest(BaseModel):
    """Payload for ``POST /api/generate/batch/plan``.

    ``urls`` may contain any strings; the validator normalizes /
    de-dupes / rejects per ``plan_batch``'s rules.  Non-strings get
    coerced to ``str`` with the same logic.
    """
    urls: List[str] = Field(
        default_factory=list,
        description=(
            f"Up to {MAX_URLS} job-posting URLs. Excess entries are "
            "returned in `rejected` with reason 'over_cap'."
        ),
    )
    min_fit_score: float = Field(
        default=MIN_FIT_SCORE_FLOOR,
        ge=MIN_FIT_SCORE_FLOOR,
        le=MIN_FIT_SCORE_CEIL,
        description=(
            "Echoed back so the client can lock the threshold it "
            "used for ranking.  Range: "
            f"[{MIN_FIT_SCORE_FLOOR}, {MIN_FIT_SCORE_CEIL}]."
        ),
    )


def _serialize_plan(plan: BatchPlan) -> Dict[str, Any]:
    """Frozen-dataclass → JSON-safe shape.

    Tuples become lists; ``ats_key`` (a 3-tuple) becomes a 3-list so
    the frontend can index it positionally without losing the order.
    """
    def _entry(e: object) -> Dict[str, Any]:
        if not is_dataclass(e):
            return {}  # defensive — shouldn't happen
        d = asdict(e)
        # asdict turns the (platform, company, job_id) tuple into a list
        # already; nothing further to coerce.
        return d

    return {
        "accepted": [_entry(e) for e in plan.accepted],
        "rejected": [_entry(e) for e in plan.rejected],
        "summary": {
            "accepted_count": len(plan.accepted),
            "rejected_count": len(plan.rejected),
            "max_urls": MAX_URLS,
            "is_empty": plan.is_empty,
        },
    }


# ── Route ────────────────────────────────────────────────────────────


@router.post("/generate/batch/plan")
@limiter.limit("10/minute")
async def plan_batch_route(
    request: Request,
    payload: BatchPlanRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Validate and dedupe a batch of URLs without scoring them.

    Returns the serialized ``BatchPlan`` plus a small ``summary``
    block.  Frontend uses this for the paste-preview step before
    triggering the actual scoring fan-out (B0.worker, next slice).

    Response shape::

        {
          "accepted": [{"raw_url", "canonical_url", "ats_key"}],
          "rejected": [{"raw_url", "reason"}],
          "summary": {"accepted_count", "rejected_count",
                      "max_urls", "is_empty"},
          "min_fit_score": float
        }
    """
    plan = plan_batch(payload.urls)
    body = _serialize_plan(plan)
    body["min_fit_score"] = payload.min_fit_score
    return body


__all__ = ["router", "BatchPlanRequest"]
