"""
Analytics routes (Firestore)
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, Query

from app.services.analytics import AnalyticsService
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get analytics dashboard data."""
    service = AnalyticsService()
    return await service.get_dashboard(current_user["id"])


@router.get("/activity")
async def get_activity(
    days: int = Query(30),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get recent activity."""
    service = AnalyticsService()
    activity = await service.get_recent_activity(current_user["id"], days)
    return {"activity": activity}


@router.get("/progress")
async def get_progress(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get user's overall progress."""
    service = AnalyticsService()
    return await service.get_progress(current_user["id"])


@router.post("/track")
async def track_event(
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Track an analytics event."""
    service = AnalyticsService()
    await service.track_event(
        user_id=current_user["id"],
        event_type=body.get("event_type", "unknown"),
        event_data=body.get("event_data", {}),
    )
    return {"status": "tracked"}


@router.get("/stats/applications")
async def get_application_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get application-related statistics."""
    service = AnalyticsService()
    return await service.get_application_stats(current_user["id"])
