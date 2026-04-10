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


@router.get("/daily-briefing")
async def get_daily_briefing(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get AI-generated daily career insight."""
    from app.core.database import get_db, TABLES
    from ai_engine.client import AIClient
    from ai_engine.chains.daily_briefing import DailyBriefingChain
    import structlog

    logger = structlog.get_logger()
    db = get_db()

    try:
        # Get profile
        profiles = await db.query(TABLES["profiles"], filters=[("user_id", "==", current_user["id"]), ("is_primary", "==", True)], limit=1)
        profile = profiles[0] if profiles else {}

        # Get app stats
        apps = await db.query(TABLES["applications"], filters=[("user_id", "==", current_user["id"])])
        avg_match = round(sum(a.get("scores", {}).get("match", 0) for a in apps) / max(len(apps), 1))

        evidence = await db.query(TABLES["evidence"], filters=[("user_id", "==", current_user["id"])])

        app_stats = {
            "app_count": len(apps),
            "avg_match": avg_match,
            "open_tasks": 0,
            "evidence_count": len(evidence),
            "recent_activity": f"Last application: {apps[0].get('title', 'N/A')}" if apps else "No applications yet",
        }

        chain = DailyBriefingChain(AIClient())
        return await chain.generate(profile, app_stats)
    except Exception as e:
        logger.warning("daily_briefing_failed", error=str(e)[:200])
        return {
            "insight": "Keep building your career portfolio — every step counts.",
            "category": "growth",
            "action_label": "View Career Nexus",
            "action_href": "/nexus",
        }
