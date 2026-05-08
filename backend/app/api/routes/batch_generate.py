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

import logging
import os
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
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
from app.services.batch_jd_fetcher import JDLoader, make_jd_loader
from app.services.batch_persister import make_batch_id, persist_ranked_batch
from app.services.batch_scorer_glue import make_llm_scorer
from app.services.batch_scorer_worker import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    Scorer,
    score_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Scorer dependency (B0.scorer.wire) ────────────────────────────────
#
# Two paths share one Depends() entry:
#
#   * Stub (default) — returns ScoringResult(error="scorer_not_configured")
#     for every entry. Safe for prod until we flip the flag and lets
#     the UI render a typed failure per row instead of throwing.
#
#   * Live — make_llm_scorer composed from real ProfileService +
#     httpx-backed Fetcher → make_jd_loader + ai_engine.client. Each
#     request gets a fresh Scorer bound to the caller's user_id; the
#     underlying singletons (httpx client, AIClient, ProfileService)
#     are cached process-wide so we don't pay re-init cost per call.
#
# Selection is via env flag ``BATCH_SCORER_LIVE`` (defaults off).
# Tests keep working as-is because they override ``get_scorer`` with
# ``lambda: my_scorer`` — that bypasses the user_id dep entirely.

_LIVE_FLAG_ENV = "BATCH_SCORER_LIVE"
_LIVE_FETCH_TIMEOUT_S = 12.0
_LIVE_USER_AGENT = (
    "HireStack/1.0 BatchScorer (+https://hirestack.ai)"
)


def _is_live_enabled() -> bool:
    val = os.getenv(_LIVE_FLAG_ENV, "").strip().lower()
    return val in ("1", "true", "yes", "on")


async def _stub_scorer(entry: BatchEntry) -> ScoringResult:
    return ScoringResult(
        canonical_url=entry.canonical_url,
        fit_score=None,
        error="scorer_not_configured",
    )


# ── Live wiring (only constructed when BATCH_SCORER_LIVE is on) ──────


async def _live_httpx_fetcher(url: str) -> str:
    """HTTP GET → response body text. Used as the Fetcher seam."""
    headers = {
        "User-Agent": _LIVE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=_LIVE_FETCH_TIMEOUT_S,
        follow_redirects=True,
        max_redirects=3,
        headers=headers,
    ) as client:
        resp = await client.get(url)
        return resp.text or ""


@lru_cache(maxsize=1)
def _shared_jd_loader() -> JDLoader:
    return make_jd_loader(fetcher=_live_httpx_fetcher)


@lru_cache(maxsize=1)
def _shared_ai_client() -> Any:
    # Imported lazily so unit tests that never enable the live flag
    # don't pay the ai_engine.client import cost.
    from ai_engine.api import get_ai_client

    return get_ai_client()


@lru_cache(maxsize=1)
def _shared_profile_service() -> Any:
    from app.services.profile import ProfileService

    return ProfileService()


async def _live_profile_loader(user_id: str) -> Optional[Dict[str, Any]]:
    svc = _shared_profile_service()
    return await svc.get_primary_profile(user_id)


def _build_live_scorer(user_id: str) -> Scorer:
    return make_llm_scorer(
        user_id=user_id,
        profile_loader=_live_profile_loader,
        jd_loader=_shared_jd_loader(),
        ai_client=_shared_ai_client(),
    )


async def get_scorer(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Scorer:
    """FastAPI dependency — the score route's Scorer.

    Returns the stub by default; returns a fully wired
    ``make_llm_scorer`` (per-request, bound to ``current_user["id"]``)
    when ``BATCH_SCORER_LIVE`` is truthy.

    Tests override this via ``app.dependency_overrides[get_scorer] =
    lambda: my_scorer`` — that bypasses the ``current_user`` dep
    entirely so test factories don't need to thread a user.
    """
    if not _is_live_enabled():
        return _stub_scorer
    user_id = current_user.get("id") if isinstance(current_user, dict) else None
    if not user_id:
        # Defensive: if auth somehow yields no id, fall back to stub
        # rather than ScoringResult-failing every entry with a confusing
        # profile_load_error.  Should never trigger in prod.
        logger.warning("batch_scorer live flag on but current_user missing id")
        return _stub_scorer
    return _build_live_scorer(user_id)


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


# ── Commit route (B0.persist.route) ──────────────────────────────────


class BatchCommitRequest(BaseModel):
    """Payload for ``POST /api/generate/batch/commit``.

    Same knobs as ``BatchScoreRequest`` — the commit endpoint runs
    the full pipeline (plan → score → rank → persist) so the client
    only needs one round-trip from "paste" to "saved".  Frontend
    can still call ``/score`` first to preview before committing.
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
    )


async def get_db_dep() -> Any:
    """FastAPI dependency that returns the shared Database client.

    Wrapped in a function so tests can override via
    ``app.dependency_overrides[get_db_dep] = lambda: fake_db``.
    Lazy import keeps the supabase client out of any test that
    overrides the dep entirely.
    """
    from app.core.database import get_db
    return get_db()


@router.post("/generate/batch/commit")
@limiter.limit("5/minute")
async def commit_batch_route(
    request: Request,
    payload: BatchCommitRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    scorer: Scorer = Depends(get_scorer),
    db: Any = Depends(get_db_dep),
) -> Dict[str, Any]:
    """Plan → score → rank → persist a batch in one call.

    Returns the same plan + scored bodies as ``/score`` plus a
    ``persisted`` block with the new ``batch_id`` and per-row
    ``application_id``.  Below-threshold and failed entries are
    NEVER persisted (enforced in ``batch_persister_core``).

    Response shape::

        {
          "plan":      <same as /plan>,
          "scored":    <same as /score>,
          "persisted": {
              "batch_id": str,
              "inserted": [{"canonical_url": str,
                            "application_id": str}],
              "inserted_count": int
          },
          "min_fit_score": float
        }

    Rate-limited at 5/min — same as ``/score`` since this is a
    superset.  Auth required (current_user.id is the row owner).

    Idempotency: a stable ``dedup_key`` lives in
    ``confirmed_facts.dedup_key`` (sha256 of ``user_id\\x1fcanonical_url``).
    A future migration will add a partial unique index; until then
    repeat pastes produce duplicate rows.  See B0.persist.idempotency.
    """
    user_id = current_user.get("id") if isinstance(current_user, dict) else None
    if not user_id:
        # Defensive — get_current_user should always provide id.
        logger.error("batch_commit missing user id")
        return {
            "plan": _serialize_plan(plan_batch([])),
            "scored": _serialize_ranked(rank_batch([])),
            "persisted": {
                "batch_id": "",
                "inserted": [],
                "inserted_count": 0,
                "skipped": [],
                "skipped_count": 0,
            },
            "min_fit_score": payload.min_fit_score,
        }

    plan = plan_batch(payload.urls)
    scored = await score_plan(
        plan.accepted,
        scorer=scorer,
        concurrency=payload.concurrency,
    )
    ranked = rank_batch(scored, min_fit_score=payload.min_fit_score)

    batch_id = make_batch_id()
    result = await persist_ranked_batch(
        db=db,
        ranked=ranked,
        user_id=str(user_id),
        batch_id=batch_id,
    )

    return {
        "plan": _serialize_plan(plan),
        "scored": _serialize_ranked(ranked),
        "persisted": {
            "batch_id": batch_id,
            "inserted": [
                {"canonical_url": url, "application_id": aid}
                for url, aid in result.inserted
            ],
            "inserted_count": result.inserted_count,
            "skipped": [
                {"canonical_url": url, "application_id": aid}
                for url, aid in result.skipped
            ],
            "skipped_count": result.skipped_count,
        },
        "min_fit_score": payload.min_fit_score,
    }


__all__ = [
    "router",
    "BatchPlanRequest",
    "BatchScoreRequest",
    "BatchCommitRequest",
    "get_scorer",
    "get_db_dep",
]
