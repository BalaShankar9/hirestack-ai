"""
Feedback & Outcome Tracking Routes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Endpoints for collecting user outcome data (ratings, application results)
that feed back into the evidence graph and adaptive planner.
"""
import asyncio
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.api.deps import get_current_user
from app.core.database import get_supabase, TABLES

logger = structlog.get_logger("hirestack.feedback")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
#  Request schemas
# ═══════════════════════════════════════════════════════════════════════

class ApplicationFeedbackRequest(BaseModel):
    """User feedback on a generated application."""
    application_id: str
    user_rating: Optional[int] = None       # 1-5 stars
    user_feedback_text: Optional[str] = None
    outcome: Optional[str] = None           # callback, offer, rejected, ghosted

    @field_validator("user_rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    @field_validator("user_feedback_text")
    @classmethod
    def validate_feedback_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 5000:
            raise ValueError("Feedback text too long (max 5000 characters)")
        return v

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"callback", "offer", "rejected", "ghosted", None}
        if v not in allowed:
            raise ValueError("Outcome must be one of: callback, offer, rejected, ghosted")
        return v


class ABTestResultRequest(BaseModel):
    """Record the outcome of an A/B document test."""
    variant_id: str
    document_type: str             # cv, cover_letter, personal_statement
    ats_score: Optional[float] = None
    readability_score: Optional[float] = None
    keyword_density: Optional[float] = None
    outcome_type: Optional[str] = None  # submitted, callback, offer

    @field_validator("document_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        allowed = {"cv", "cover_letter", "personal_statement", "portfolio"}
        if v not in allowed:
            raise ValueError(f"Document type must be one of: {', '.join(allowed)}")
        return v


# ═══════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════

@router.post("/application")
async def submit_application_feedback(
    req: ApplicationFeedbackRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Submit feedback and outcome data for a generated application.

    Updates the application record with rating, feedback text, and outcome
    timestamps (callback_received_at, offer_received_at).
    """
    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Verify application belongs to user
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id, user_id")
        .eq("id", req.application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    update: Dict[str, Any] = {}
    now = datetime.now(timezone.utc).isoformat()

    if req.user_rating is not None:
        update["user_rating"] = req.user_rating
    if req.user_feedback_text is not None:
        update["user_feedback_text"] = req.user_feedback_text
    if req.outcome == "callback":
        update["callback_received_at"] = now
    elif req.outcome == "offer":
        update["offer_received_at"] = now

    if not update:
        raise HTTPException(status_code=400, detail="No feedback data provided")

    await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .update(update)
        .eq("id", req.application_id)
        .execute()
    )

    logger.info(
        "feedback.application_submitted",
        application_id=req.application_id,
        user_id=user_id,
        rating=req.user_rating,
        outcome=req.outcome,
    )

    # ── Outcome → Evidence Graph feedback loop ────────────────────
    evidence_feedback = None
    if req.outcome:
        try:
            from ai_engine.agents.evidence_graph import EvidenceGraphBuilder
            builder = EvidenceGraphBuilder(db=sb, user_id=user_id)
            evidence_feedback = builder.apply_outcome_feedback(
                outcome=req.outcome,
                job_id=None,  # Apply to all user evidence (cross-job learning)
            )
        except Exception as e:
            logger.warning("feedback.evidence_loop_failed", error=str(e)[:200])

    return {
        "status": "ok",
        "updated_fields": list(update.keys()),
        "evidence_feedback": evidence_feedback,
    }


@router.post("/ab-test")
async def record_ab_test_result(
    req: ABTestResultRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Record the result of an A/B document variant test."""
    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    row = {
        "user_id": user_id,
        "variant_id": req.variant_id,
        "document_type": req.document_type,
        "ats_score": req.ats_score,
        "readability_score": req.readability_score,
        "keyword_density": req.keyword_density,
        "outcome_type": req.outcome_type,
    }

    await asyncio.to_thread(
        lambda: sb.table("ab_test_results")
        .insert(row)
        .execute()
    )

    logger.info(
        "feedback.ab_test_recorded",
        variant_id=req.variant_id,
        document_type=req.document_type,
        user_id=user_id,
    )

    return {"status": "ok"}


@router.get("/ab-test/stats")
async def get_ab_test_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get A/B test comparison analytics for the current user.

    Returns per-document-type stats: variant count, average scores,
    and outcome distribution.
    """
    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    try:
        resp = await asyncio.to_thread(
            lambda: sb.table("ab_test_results")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return {"document_types": {}, "total_variants": 0}

        # Group by document_type
        by_type: Dict[str, List[Dict]] = {}
        for row in rows:
            dt = row.get("document_type", "unknown")
            by_type.setdefault(dt, []).append(row)

        stats: Dict[str, Any] = {}
        for doc_type, variants in by_type.items():
            ats_scores = [v["ats_score"] for v in variants if v.get("ats_score") is not None]
            readability = [v["readability_score"] for v in variants if v.get("readability_score") is not None]
            outcomes = {}
            for v in variants:
                ot = v.get("outcome_type")
                if ot:
                    outcomes[ot] = outcomes.get(ot, 0) + 1

            stats[doc_type] = {
                "variant_count": len(variants),
                "avg_ats_score": round(sum(ats_scores) / len(ats_scores), 2) if ats_scores else None,
                "avg_readability": round(sum(readability) / len(readability), 2) if readability else None,
                "outcome_distribution": outcomes,
            }

        return {
            "document_types": stats,
            "total_variants": len(rows),
        }
    except Exception as e:
        logger.warning("feedback.ab_stats_failed", error=str(e)[:200])
        return {"document_types": {}, "total_variants": 0}


@router.get("/stats")
async def get_feedback_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get aggregated feedback stats for the current user."""
    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    try:
        apps_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["applications"])
            .select("user_rating, callback_received_at, offer_received_at")
            .eq("user_id", user_id)
            .not_.is_("user_rating", "null")
            .execute()
        )
        apps = apps_resp.data or []

        ratings = [a["user_rating"] for a in apps if a.get("user_rating")]
        callbacks = sum(1 for a in apps if a.get("callback_received_at"))
        offers = sum(1 for a in apps if a.get("offer_received_at"))

        return {
            "total_rated": len(ratings),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "callbacks": callbacks,
            "offers": offers,
        }
    except Exception as e:
        logger.warning("feedback.stats_failed", error=str(e)[:200])
        return {"total_rated": 0, "average_rating": None, "callbacks": 0, "offers": 0}
