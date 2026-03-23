"""
Benchmark routes - Generate ideal candidate benchmarks (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.services.benchmark import BenchmarkService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class GenerateBenchmarkRequest(BaseModel):
    job_description_id: Optional[str] = Field(None, max_length=100)
    job_id: Optional[str] = Field(None, max_length=100)

    @field_validator("job_description_id", "job_id")
    @classmethod
    def validate_uuids(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                _uuid.UUID(v)
            except (ValueError, AttributeError):
                raise ValueError("must be a valid UUID")
        return v


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_benchmark(
    request: Request,
    body: GenerateBenchmarkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a complete benchmark package for a job."""
    service = BenchmarkService()
    job_id = body.job_description_id or body.job_id
    if not job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_description_id is required")
    try:
        return await service.generate_benchmark(user_id=current_user["id"], job_id=job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Benchmark generation failed. Please check your inputs.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate benchmark. Please try again.")


@router.get("/{benchmark_id}")
@limiter.limit("30/minute")
async def get_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific benchmark."""
    _validate_uuid(benchmark_id, "benchmark_id")
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
    _validate_uuid(job_id, "job_id")
    service = BenchmarkService()
    benchmark = await service.get_benchmark_for_job(job_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark found for this job.")
    return benchmark


@router.post("/{benchmark_id}/regenerate")
@limiter.limit("5/minute")
async def regenerate_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Regenerate a benchmark."""
    _validate_uuid(benchmark_id, "benchmark_id")
    service = BenchmarkService()
    benchmark = await service.regenerate_benchmark(benchmark_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return benchmark


@router.delete("/{benchmark_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_benchmark(
    request: Request,
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a benchmark."""
    _validate_uuid(benchmark_id, "benchmark_id")
    service = BenchmarkService()
    deleted = await service.delete_benchmark(benchmark_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
