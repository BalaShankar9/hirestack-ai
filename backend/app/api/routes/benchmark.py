"""
Benchmark routes - Generate ideal candidate benchmarks (Firestore)
"""
from typing import Dict, Any

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field

from app.services.benchmark import BenchmarkService
from app.api.deps import get_current_user, validate_uuid
from app.api.response import success_response
import structlog

logger = structlog.get_logger()

router = APIRouter()


class GenerateBenchmarkRequest(BaseModel):
    job_description_id: str = Field(..., min_length=1, max_length=100)


@router.post("/generate")
@limiter.limit("3/minute")
async def generate_benchmark(
    request: Request,
    body: GenerateBenchmarkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a complete benchmark package for a job."""
    service = BenchmarkService()
    try:
        benchmark = await service.generate_benchmark(user_id=current_user["id"], job_id=body.job_description_id)
        return success_response(benchmark)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="generate_benchmark")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@router.get("/{benchmark_id}")
@limiter.limit("30/minute")
async def get_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific benchmark."""
    validate_uuid(benchmark_id, "benchmark_id")
    service = BenchmarkService()
    benchmark = await service.get_benchmark(benchmark_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return benchmark


@router.get("/job/{job_id}")
@limiter.limit("30/minute")
async def get_benchmark_for_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get benchmark for a specific job."""
    validate_uuid(job_id, "job_id")
    service = BenchmarkService()
    benchmark = await service.get_benchmark_for_job(job_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark found for this job.")
    return benchmark


@router.post("/{benchmark_id}/regenerate")
@limiter.limit("3/minute")
async def regenerate_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Regenerate a benchmark."""
    validate_uuid(benchmark_id, "benchmark_id")
    service = BenchmarkService()
    benchmark = await service.regenerate_benchmark(benchmark_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return benchmark


@router.delete("/{benchmark_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a benchmark."""
    validate_uuid(benchmark_id, "benchmark_id")
    service = BenchmarkService()
    deleted = await service.delete_benchmark(benchmark_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
