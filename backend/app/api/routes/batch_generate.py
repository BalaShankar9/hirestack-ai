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
    BatchEntry,
    BatchPlan,
    RankedBatch,
    ScoringResult,
    plan_batch,
    rank_batch,
)
from app.services.batch_scorer_worker import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    Scorer,
    score_plan,
)

router = APIRouter()


# ── Scorer dependency ────────────────────────────────────────────────
#
# The real scorer (LLM chain hitting the AI router) is not yet wired —
# that is its own slice (B0.scorer) so that the route + contract +
# rate limit can ship now and tests stay AI-free.  The default scorer
# returns a typed failure so a misconfigured prod deploy doesn't
# silently return zeros; the route still 200s with a fully populated
# `failed` bucket so the UI can render "scoring backend unavailable"
# per row instead of choking on an exception.


async def _stub_scorer(entry: BatchEntry) -> ScoringResult:
    return ScoringResult(
        canonical_url=entry.canonical_url,
        fit_score=None,
        error="scorer_not_configured",
    )


def get_scorer() -> Scorer:
    """FastAPI dependency — override in tests via app.dependency_overrides."""
    return _stub_scorer


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


# ── Score route ──────────────────────────────────────────────────────


class BatchScoreRequest(BaseModel):
    """Payload for ``POST /api/generate/batch/score``.

    Same shape as ``BatchPlanRequest`` plus an optional concurrency
    knob.  Concurrency is clamped inside ``score_plan`` to
    ``[1, MAX_CONCURRENCY]`` regardless of what the caller passes,
    so an over-eager client cannot drain the AI rate-limit budget.
    """
    urls: List[str] = Field(default_factory=list)
    min_fit_score: float = Field(
        default=MIN_FIT_SCORE_FLOOR,
        ge=MIN_FIT_SCORE_FLOOR,
        le=MIN_FIT_SCORE_CEIL,
    )
    concurrency: int = Field(
        default=DEFAULT_CONCURRENCY,
        ge=1,
        le=MAX_CONCURRENCY,
        description=(
            f"Parallel scorer slots. Range: [1, {MAX_CONCURRENCY}]. "
            f"Default: {DEFAULT_CONCURRENCY}."
        ),
    )


def _serialize_scoring_result(r: ScoringResult) -> Dict[str, Any]:
    return {
        "canonical_url": r.canonical_url,
        "fit_score": r.fit_score,
        "error": r.error,
        "title": r.title,
        "company": r.company,
    }


def _serialize_ranked(ranked: RankedBatch) -> Dict[str, Any]:
    return {
        "ranked": [_serialize_scoring_result(r) for r in ranked.ranked],
        "below_threshold": [_serialize_scoring_result(r) for r in ranked.below_threshold],
        "failed": [_serialize_scoring_result(r) for r in ranked.failed],
        "summary": {
            "ranked_count": len(ranked.ranked),
            "below_threshold_count": len(ranked.below_threshold),
            "failed_count": len(ranked.failed),
        },
    }


@router.post("/generate/batch/score")
@limiter.limit("5/minute")
async def score_batch_route(
    request: Request,
    payload: BatchScoreRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    scorer: Scorer = Depends(get_scorer),
) -> Dict[str, Any]:
    """Validate, score, and rank a batch of URLs in one shot.

    Pipeline:
        1. ``plan_batch`` — validate / canonicalize / dedupe URLs.
        2. ``score_plan`` — fan out to the injected ``Scorer`` under
           a concurrency cap.  Per-entry failures become
           ``ScoringResult(error=...)`` and route to ``failed``.
        3. ``rank_batch`` — bucket into ``ranked`` (>= threshold,
           sorted desc), ``below_threshold`` (< threshold, sorted
           desc), and ``failed``.

    Response shape::

        {
          "plan":   <same shape as /plan response>,
          "scored": {
              "ranked":          [ScoringResult, ...],
              "below_threshold": [ScoringResult, ...],
              "failed":          [ScoringResult, ...],
              "summary": {ranked_count, below_threshold_count,
                          failed_count}
          },
          "min_fit_score": float
        }

    Rate-limited at 5/min (half of /plan): scoring is the expensive
    side and we don't want a paste bot draining the AI budget.

    Persistence (writing the ranked rows into ``applications``) is
    the next slice (B0.persist) — keeping it out of this route means
    the score route stays idempotent and safe to retry.
    """
    plan = plan_batch(payload.urls)
    scored = await score_plan(
        plan.accepted,
        scorer=scorer,
        concurrency=payload.concurrency,
    )
    ranked = rank_batch(scored, min_fit_score=payload.min_fit_score)

    return {
        "plan": _serialize_plan(plan),
        "scored": _serialize_ranked(ranked),
        "min_fit_score": payload.min_fit_score,
    }


__all__ = [
    "router",
    "BatchPlanRequest",
    "BatchScoreRequest",
    "get_scorer",
]
