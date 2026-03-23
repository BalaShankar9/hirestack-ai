"""
Job Description routes (Supabase)
Security: rate limiting, Pydantic input validation, UUID checks.
"""
import logging
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.job import get_job_service
from app.api.deps import get_current_user
from app.core.security import limiter

logger = logging.getLogger("hirestack.jobs")

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────

class CreateJobBody(BaseModel):
    title: str = Field(..., max_length=255)
    company: str = Field("", max_length=255)
    location: str = Field("", max_length=255)
    job_type: str = Field("", max_length=50)
    experience_level: str = Field("", max_length=50)
    salary_range: str = Field("", max_length=100)
    description: str = Field("", max_length=50_000)
    source_url: str = Field("", max_length=2048)


class UpdateJobBody(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    company: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    job_type: Optional[str] = Field(None, max_length=50)
    experience_level: Optional[str] = Field(None, max_length=50)
    salary_range: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=50_000)
    source_url: Optional[str] = Field(None, max_length=2048)


def _validate_uuid(value: str, label: str = "ID") -> str:
    """Validate and normalize a UUID string."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {label}: must be a valid UUID.",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_job(
    request: Request,
    body: CreateJobBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new job description."""
    service = get_job_service()
    return await service.create_job(current_user["id"], body.model_dump(exclude_none=True))


@router.get("")
@limiter.limit("60/minute")
async def list_jobs(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's job descriptions."""
    service = get_job_service()
    return await service.get_user_jobs(current_user["id"])


@router.get("/{job_id}")
@limiter.limit("60/minute")
async def get_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific job description."""
    job_id = _validate_uuid(job_id, "job_id")
    service = get_job_service()
    job = await service.get_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job


@router.put("/{job_id}")
@limiter.limit("30/minute")
async def update_job(
    request: Request,
    job_id: str,
    body: UpdateJobBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a job description."""
    job_id = _validate_uuid(job_id, "job_id")
    service = get_job_service()
    job = await service.update_job(job_id, current_user["id"], body.model_dump(exclude_none=True))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a job description."""
    job_id = _validate_uuid(job_id, "job_id")
    service = get_job_service()
    deleted = await service.delete_job(job_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")


@router.post("/{job_id}/parse")
@limiter.limit("10/minute")
async def parse_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Parse a job description with AI to extract requirements."""
    job_id = _validate_uuid(job_id, "job_id")
    service = get_job_service()
    try:
        job = await service.parse_job(job_id, current_user["id"])
    except Exception as e:
        logger.warning("job_parse_failed", extra={"job_id": job_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse job description. Please try again.",
        )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job
