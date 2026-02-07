"""
Benchmark routes - Generate ideal candidate benchmarks (Firestore)
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.benchmark import BenchmarkService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/generate")
async def generate_benchmark(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a complete benchmark package for a job."""
    service = BenchmarkService()
    job_id = request.get("job_description_id") or request.get("job_id")
    if not job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_description_id is required")
    try:
        return await service.generate_benchmark(user_id=current_user["id"], job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate benchmark: {e}")


@router.get("/{benchmark_id}")
async def get_benchmark(
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific benchmark."""
    service = BenchmarkService()
    benchmark = await service.get_benchmark(benchmark_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return benchmark


@router.get("/job/{job_id}")
async def get_benchmark_for_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get benchmark for a specific job."""
    service = BenchmarkService()
    benchmark = await service.get_benchmark_for_job(job_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No benchmark found for this job.")
    return benchmark


@router.post("/{benchmark_id}/regenerate")
async def regenerate_benchmark(
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Regenerate a benchmark."""
    service = BenchmarkService()
    benchmark = await service.regenerate_benchmark(benchmark_id, current_user["id"])
    if not benchmark:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
    return benchmark


@router.delete("/{benchmark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_benchmark(
    benchmark_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a benchmark."""
    service = BenchmarkService()
    deleted = await service.delete_benchmark(benchmark_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found")
