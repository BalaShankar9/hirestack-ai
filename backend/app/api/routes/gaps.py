"""
Gap Analysis routes
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.gap import GapAnalysisRequest, GapReportResponse, GapSummary
from app.services.gap import GapService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/analyze", response_model=GapReportResponse)
async def analyze_gaps(
    request: GapAnalysisRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform gap analysis comparing profile to benchmark."""
    gap_service = GapService(db)

    try:
        report = await gap_service.analyze_gaps(
            user_id=current_user.id,
            profile_id=request.profile_id,
            benchmark_id=request.benchmark_id
        )
        return report
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze gaps: {str(e)}"
        )


@router.get("", response_model=List[GapReportResponse])
async def list_gap_reports(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's gap reports."""
    gap_service = GapService(db)
    reports = await gap_service.get_user_reports(current_user.id)
    return reports


@router.get("/{report_id}", response_model=GapReportResponse)
async def get_gap_report(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific gap report."""
    gap_service = GapService(db)
    report = await gap_service.get_report(report_id, current_user.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gap report not found"
        )
    return report


@router.get("/{report_id}/summary", response_model=GapSummary)
async def get_gap_summary(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a summary of a gap report."""
    gap_service = GapService(db)
    summary = await gap_service.get_summary(report_id, current_user.id)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gap report not found"
        )
    return summary


@router.post("/{report_id}/refresh", response_model=GapReportResponse)
async def refresh_gap_analysis(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh a gap analysis with latest data."""
    gap_service = GapService(db)
    report = await gap_service.refresh_analysis(report_id, current_user.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gap report not found"
        )
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gap_report(
    report_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a gap report."""
    gap_service = GapService(db)
    deleted = await gap_service.delete_report(report_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gap report not found"
        )
