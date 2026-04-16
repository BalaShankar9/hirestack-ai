"""
Micro-Learning routes - Daily challenges and streak tracking (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.learning import LearningService
from app.api.deps import get_current_user
from app.core.security import limiter
import structlog

logger = structlog.get_logger()

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class GenerateChallengesRequest(BaseModel):
    skills: Optional[List[str]] = None
    count: int = Field(5, ge=1, le=20)
    job_context: str = Field("software engineering", max_length=500)


class SubmitAnswerRequest(BaseModel):
    user_answer: str = Field(..., max_length=10_000)


@limiter.limit("30/minute")
@router.get("/streak")
async def get_streak(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the user's learning streak."""
    service = LearningService()
    return await service.get_or_create_streak(current_user["id"])


@limiter.limit("5/minute")
@router.post("/generate")
async def generate_daily_challenges(
    request: Request,
    body: GenerateChallengesRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a daily set of learning challenges."""
    service = LearningService()
    try:
        return await service.generate_daily_challenges(
            user_id=current_user["id"],
            skills=body.skills,
            count=body.count,
            job_context=body.job_context,
        )
    except Exception as e:
        logger.error("challenge_generation_failed", error=str(e), user_id=current_user["id"])
        raise HTTPException(status_code=500, detail="Challenge generation failed. Please try again.")


@limiter.limit("30/minute")
@router.post("/{challenge_id}/answer")
async def submit_answer(
    request: Request,
    challenge_id: str,
    body: SubmitAnswerRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Submit an answer to a challenge."""
    _validate_uuid(challenge_id, "challenge_id")
    service = LearningService()
    try:
        return await service.submit_answer(
            user_id=current_user["id"],
            challenge_id=challenge_id,
            user_answer=body.user_answer,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Challenge not found or already completed.")


@limiter.limit("30/minute")
@router.get("/today")
async def get_today_challenges(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get today's challenges."""
    service = LearningService()
    return await service.get_today_challenges(current_user["id"])


@limiter.limit("30/minute")
@router.get("/history")
async def get_history(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get challenge history."""
    service = LearningService()
    return await service.get_history(current_user["id"], limit)
