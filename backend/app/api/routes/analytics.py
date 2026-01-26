"""
Analytics routes
"""
from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.services.analytics import AnalyticsService
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics dashboard data."""
    analytics_service = AnalyticsService(db)
    dashboard = await analytics_service.get_dashboard(current_user.id)
    return dashboard


@router.get("/activity")
async def get_activity(
    days: int = 30,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent activity."""
    analytics_service = AnalyticsService(db)
    activity = await analytics_service.get_recent_activity(current_user.id, days)
    return {"activity": activity}


@router.get("/progress")
async def get_progress(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's overall progress."""
    analytics_service = AnalyticsService(db)
    progress = await analytics_service.get_progress(current_user.id)
    return progress


@router.post("/track")
async def track_event(
    event_type: str,
    event_data: Dict[str, Any] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Track an analytics event."""
    analytics_service = AnalyticsService(db)
    await analytics_service.track_event(
        user_id=current_user.id,
        event_type=event_type,
        event_data=event_data or {}
    )
    return {"status": "tracked"}


@router.get("/stats/applications")
async def get_application_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get application-related statistics."""
    analytics_service = AnalyticsService(db)
    stats = await analytics_service.get_application_stats(current_user.id)
    return stats
