"""
Gap Analysis routes (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.services.gap import GapService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class AnalyzeGapsRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100)
    benchmark_id: str = Field(..., min_length=1, max_length=100)

    @field_validator("profile_id", "benchmark_id")
    @classmethod
    def validate_uuids(cls, v: str) -> str:
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError("must be a valid UUID")
        return v


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze_gaps(
    request: Request,
    body: AnalyzeGapsRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Perform gap analysis comparing profile to benchmark."""
    service = GapService()
    try:
        return await service.analyze_gaps(user_id=current_user["id"], profile_id=body.profile_id, benchmark_id=body.benchmark_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gap analysis failed. Please check your inputs.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to analyze gaps. Please try again.")


@router.get("")
@limiter.limit("30/minute")
async def list_gap_reports(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's gap reports."""
    service = GapService()
    return await service.get_user_reports(current_user["id"])


@router.get("/{report_id}")
@limiter.limit("30/minute")
async def get_gap_report(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific gap report."""
    _validate_uuid(report_id, "report_id")
    service = GapService()
    report = await service.get_report(report_id, current_user["id"])
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
    return report


@router.get("/{report_id}/summary")
@limiter.limit("30/minute")
async def get_gap_summary(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a summary of a gap report."""
    _validate_uuid(report_id, "report_id")
    service = GapService()
    summary = await service.get_summary(report_id, current_user["id"])
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
    return summary


@router.post("/{report_id}/refresh")
@limiter.limit("5/minute")
async def refresh_gap_analysis(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Refresh a gap analysis with latest data."""
    _validate_uuid(report_id, "report_id")
    service = GapService()
    report = await service.refresh_analysis(report_id, current_user["id"])
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_gap_report(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a gap report."""
    _validate_uuid(report_id, "report_id")
    service = GapService()
    deleted = await service.delete_report(report_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
