"""
Career Analytics routes - Timeline, trends, and portfolio (Supabase)
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.career_analytics import CareerAnalyticsService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


@router.post("/snapshot")
@limiter.limit("10/minute")
async def capture_snapshot(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Capture a daily career progress snapshot."""
    service = CareerAnalyticsService()
    return await service.capture_snapshot(current_user["id"])


@router.get("/timeline")
@limiter.limit("30/minute")
async def get_timeline(
    request: Request,
    days: int = Query(90, ge=1, le=365),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get career progress timeline."""
    service = CareerAnalyticsService()
    return await service.get_timeline(current_user["id"], days)


@router.get("/portfolio")
@limiter.limit("30/minute")
async def get_portfolio_summary(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get comprehensive career portfolio summary."""
    service = CareerAnalyticsService()
    return await service.get_portfolio_summary(current_user["id"])
