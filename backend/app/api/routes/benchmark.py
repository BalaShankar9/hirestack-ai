"""
Benchmark routes - Generate ideal candidate benchmarks
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.benchmark import BenchmarkCreate, BenchmarkResponse, BenchmarkSummary
from app.services.benchmark import BenchmarkService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/generate", response_model=BenchmarkResponse)
async def generate_benchmark(
    request: BenchmarkCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a complete benchmark package for a job."""
    benchmark_service = BenchmarkService(db)

    try:
        benchmark = await benchmark_service.generate_benchmark(
            user_id=current_user.id,
            job_id=request.job_description_id
        )
        return benchmark
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate benchmark: {str(e)}"
        )


@router.get("/{benchmark_id}", response_model=BenchmarkResponse)
async def get_benchmark(
    benchmark_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific benchmark."""
    benchmark_service = BenchmarkService(db)
    benchmark = await benchmark_service.get_benchmark(benchmark_id, current_user.id)

    if not benchmark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark not found"
        )
    return benchmark


@router.get("/job/{job_id}", response_model=BenchmarkResponse)
async def get_benchmark_for_job(
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get benchmark for a specific job."""
    benchmark_service = BenchmarkService(db)
    benchmark = await benchmark_service.get_benchmark_for_job(job_id, current_user.id)

    if not benchmark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No benchmark found for this job. Generate one first."
        )
    return benchmark


@router.post("/{benchmark_id}/regenerate", response_model=BenchmarkResponse)
async def regenerate_benchmark(
    benchmark_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate a benchmark."""
    benchmark_service = BenchmarkService(db)
    benchmark = await benchmark_service.regenerate_benchmark(benchmark_id, current_user.id)

    if not benchmark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark not found"
        )
    return benchmark


@router.delete("/{benchmark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_benchmark(
    benchmark_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a benchmark."""
    benchmark_service = BenchmarkService(db)
    deleted = await benchmark_service.delete_benchmark(benchmark_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark not found"
        )
