"""
Job Description routes
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.job import (
    JobDescriptionCreate, JobDescriptionUpdate, JobDescriptionResponse
)
from app.services.job import JobService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobDescriptionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new job description."""
    job_service = JobService(db)
    job = await job_service.create_job(current_user.id, job_data)
    return job


@router.get("", response_model=List[JobDescriptionResponse])
async def list_jobs(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's job descriptions."""
    job_service = JobService(db)
    jobs = await job_service.get_user_jobs(current_user.id)
    return jobs


@router.get("/{job_id}", response_model=JobDescriptionResponse)
async def get_job(
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific job description."""
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found"
        )
    return job


@router.put("/{job_id}", response_model=JobDescriptionResponse)
async def update_job(
    job_id: UUID,
    job_data: JobDescriptionUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a job description."""
    job_service = JobService(db)
    job = await job_service.update_job(job_id, current_user.id, job_data)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found"
        )
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a job description."""
    job_service = JobService(db)
    deleted = await job_service.delete_job(job_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found"
        )


@router.post("/{job_id}/parse", response_model=JobDescriptionResponse)
async def parse_job(
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Parse a job description with AI to extract requirements."""
    job_service = JobService(db)
    job = await job_service.parse_job(job_id, current_user.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found"
        )
    return job
