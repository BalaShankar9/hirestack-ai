"""
Job Description routes (Firestore)
"""
from typing import Dict, Any, Optional

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel, Field

from app.services.job import JobService
from app.api.deps import get_current_user, validate_uuid


class JobDataRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    company: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=500)
    job_type: Optional[str] = Field(None, max_length=100)
    experience_level: Optional[str] = Field(None, max_length=100)
    salary_range: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=50000)
    source_url: Optional[str] = Field(None, max_length=2000)


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_job(
    request: Request,
    job_data: JobDataRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new job description."""
    service = JobService()
    result = await service.create_job(current_user["id"], job_data.model_dump(exclude_none=True))
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"jobs:list:{current_user['id']}")
    return result


@router.get("")
@limiter.limit("30/minute")
async def list_jobs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's job descriptions."""
    from app.core.database import cache_get, cache_set
    cache_key = f"jobs:list:{current_user['id']}:{limit}:{offset}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    service = JobService()
    result = await service.get_user_jobs(current_user["id"], limit=limit, offset=offset)
    await cache_set(cache_key, result, ttl=60)
    return result


@router.get("/{job_id}")
@limiter.limit("30/minute")
async def get_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific job description."""
    validate_uuid(job_id, "job_id")
    service = JobService()
    job = await service.get_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job


@router.put("/{job_id}")
@limiter.limit("30/minute")
async def update_job(
    request: Request,
    job_id: str,
    job_data: JobDataRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a job description."""
    validate_uuid(job_id, "job_id")
    service = JobService()
    job = await service.update_job(job_id, current_user["id"], job_data.model_dump(exclude_none=True))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"jobs:list:{current_user['id']}")
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a job description."""
    validate_uuid(job_id, "job_id")
    service = JobService()
    deleted = await service.delete_job(job_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"jobs:list:{current_user['id']}")


@router.post("/{job_id}/parse")
@limiter.limit("30/minute")
async def parse_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Parse a job description with AI to extract requirements."""
    validate_uuid(job_id, "job_id")
    service = JobService()
    job = await service.parse_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job
