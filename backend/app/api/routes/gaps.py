"""
Gap Analysis routes (Firestore)
"""
from typing import Dict, Any

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.services.gap import GapService
from app.api.deps import get_current_user, check_billing_limit
from app.api.response import success_response
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

router = APIRouter()


class GapAnalysisRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100)
    benchmark_id: str = Field(..., min_length=1, max_length=100)


@router.post("/analyze")
@limiter.limit("3/minute")
async def analyze_gaps(
    request: Request,
    body: GapAnalysisRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Perform gap analysis comparing profile to benchmark."""
    await check_billing_limit("ai_calls", current_user)
    service = GapService()
    try:
        report = await service.analyze_gaps(user_id=current_user["id"], profile_id=body.profile_id, benchmark_id=body.benchmark_id)
        return success_response(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="analyze_gaps")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


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
    service = GapService()
    summary = await service.get_summary(report_id, current_user["id"])
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
    return summary


@router.post("/{report_id}/refresh")
@limiter.limit("30/minute")
async def refresh_gap_analysis(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Refresh a gap analysis with latest data."""
    service = GapService()
    report = await service.refresh_analysis(report_id, current_user["id"])
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_gap_report(
    request: Request,
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a gap report."""
    service = GapService()
    deleted = await service.delete_report(report_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
