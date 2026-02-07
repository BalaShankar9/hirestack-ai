"""
Job Description routes (Firestore)
"""
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.job import JobService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new job description."""
    service = JobService()
    return await service.create_job(current_user["id"], job_data)


@router.get("")
async def list_jobs(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's job descriptions."""
    service = JobService()
    return await service.get_user_jobs(current_user["id"])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific job description."""
    service = JobService()
    job = await service.get_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job


@router.put("/{job_id}")
async def update_job(
    job_id: str,
    job_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a job description."""
    service = JobService()
    job = await service.update_job(job_id, current_user["id"], job_data)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a job description."""
    service = JobService()
    deleted = await service.delete_job(job_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")


@router.post("/{job_id}/parse")
async def parse_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Parse a job description with AI to extract requirements."""
    service = JobService()
    job = await service.parse_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found")
    return job
