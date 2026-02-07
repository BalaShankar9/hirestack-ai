"""
Gap Analysis routes (Firestore)
"""
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.gap import GapService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/analyze")
async def analyze_gaps(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Perform gap analysis comparing profile to benchmark."""
    service = GapService()
    profile_id = request.get("profile_id")
    benchmark_id = request.get("benchmark_id")
    if not profile_id or not benchmark_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_id and benchmark_id are required")
    try:
        return await service.analyze_gaps(user_id=current_user["id"], profile_id=profile_id, benchmark_id=benchmark_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to analyze gaps: {e}")


@router.get("")
async def list_gap_reports(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's gap reports."""
    service = GapService()
    return await service.get_user_reports(current_user["id"])


@router.get("/{report_id}")
async def get_gap_report(
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
async def get_gap_summary(
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
async def refresh_gap_analysis(
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
async def delete_gap_report(
    report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a gap report."""
    service = GapService()
    deleted = await service.delete_report(report_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap report not found")
