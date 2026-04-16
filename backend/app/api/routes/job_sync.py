"""
Job Sync routes - Job alerts and match scoring (Supabase)
Security: rate limiting, Pydantic validation, UUID checks, enum status.
"""
import logging
import uuid
from typing import Dict, Any, Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.job_sync import get_job_sync_service
from app.api.deps import get_current_user
from app.core.security import limiter

logger = logging.getLogger("hirestack.job_sync")

router = APIRouter()

# ── Valid status values ───────────────────────────────────────────
VALID_MATCH_STATUSES = {"new", "interested", "applied", "rejected", "saved"}


class CreateAlertRequest(BaseModel):
    keywords: List[str] = Field(..., max_length=50)
    location: str = Field("", max_length=255)
    job_type: str = Field("", max_length=50)
    salary_min: float = 0
    experience_level: str = Field("", max_length=50)


class ScoreMatchRequest(BaseModel):
    job_title: str = Field(..., max_length=500)
    company: str = Field("", max_length=255)
    description: str = Field("", max_length=50_000)
    location: str = Field("", max_length=255)
    salary_range: str = Field("", max_length=100)
    source_url: str = Field("", max_length=2048)
    source: str = Field("manual", max_length=50)
    alert_id: Optional[str] = None


class UpdateMatchStatusRequest(BaseModel):
    status: Literal["new", "interested", "applied", "rejected", "saved"]


def _validate_uuid(value: str, label: str = "ID") -> str:
    """Validate and normalize a UUID string."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {label}: must be a valid UUID.",
        )


@limiter.limit("20/minute")
@router.post("/alerts")
async def create_alert(
    request: Request,
    body: CreateAlertRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a job alert."""
    service = get_job_sync_service()
    return await service.create_alert(
        user_id=current_user["id"],
        keywords=body.keywords,
        location=body.location,
        job_type=body.job_type,
        salary_min=body.salary_min,
        experience_level=body.experience_level,
    )


@limiter.limit("60/minute")
@router.get("/alerts")
async def get_alerts(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get all job alerts."""
    service = get_job_sync_service()
    return await service.get_alerts(current_user["id"])


@limiter.limit("10/minute")
@router.post("/match")
async def score_match(
    request: Request,
    body: ScoreMatchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Score a job against the user's profile."""
    service = get_job_sync_service()
    try:
        return await service.score_match(
            user_id=current_user["id"],
            job_title=body.job_title,
            company=body.company,
            description=body.description,
            location=body.location,
            salary_range=body.salary_range,
            source_url=body.source_url,
            source=body.source,
            alert_id=body.alert_id,
        )
    except Exception as e:
        logger.warning("match_scoring_failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail="Match scoring failed. Please try again.",
        )


@limiter.limit("60/minute")
@router.get("/matches")
async def get_matches(
    request: Request,
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get job matches."""
    if status and status not in VALID_MATCH_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_MATCH_STATUSES))}",
        )
    service = get_job_sync_service()
    return await service.get_matches(current_user["id"], status)


@limiter.limit("30/minute")
@router.put("/matches/{match_id}/status")
async def update_match_status(
    request: Request,
    match_id: str,
    body: UpdateMatchStatusRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a job match status."""
    match_id = _validate_uuid(match_id, "match_id")
    service = get_job_sync_service()
    success = await service.update_match_status(match_id, current_user["id"], body.status)
    if not success:
        raise HTTPException(status_code=404, detail="Match not found")
    return {"status": "updated", "new_status": body.status}
