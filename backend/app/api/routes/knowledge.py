"""
Knowledge Library API routes — browse resources, track progress, get recommendations.
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.knowledge_library import KnowledgeLibraryService
from app.api.deps import get_current_user
from app.core.security import limiter
import structlog

logger = structlog.get_logger()

router = APIRouter()


class SaveProgressRequest(BaseModel):
    resource_id: str = Field(..., min_length=1, max_length=100)
    status: str = Field("saved", pattern="^(saved|in_progress|completed)$")
    progress_pct: int = Field(0, ge=0, le=100)


class RateResourceRequest(BaseModel):
    resource_id: str = Field(..., min_length=1, max_length=100)
    rating: int = Field(..., ge=1, le=5)


# ── Resource catalog ─────────────────────────────────────────────────

@router.get("/resources")
@limiter.limit("60/minute")
async def list_resources(
    request: Request,
    category: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None, alias="type"),
    difficulty: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    featured: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Browse the knowledge library catalog."""
    svc = KnowledgeLibraryService()
    return await svc.list_resources(
        category=category,
        resource_type=resource_type,
        difficulty=difficulty,
        skill=skill,
        search=search,
        featured_only=featured,
        limit=limit,
        offset=offset,
    )


@router.get("/resources/{resource_id}")
@limiter.limit("60/minute")
async def get_resource(
    request: Request,
    resource_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a single knowledge resource."""
    svc = KnowledgeLibraryService()
    resource = await svc.get_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


# ── User progress ────────────────────────────────────────────────────

@router.get("/progress")
@limiter.limit("30/minute")
async def get_progress(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the user's knowledge library progress (saved, in-progress, completed)."""
    svc = KnowledgeLibraryService()
    return await svc.get_user_progress(current_user["id"])


@router.post("/progress")
@limiter.limit("30/minute")
async def save_progress(
    request: Request,
    body: SaveProgressRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Save or update progress on a knowledge resource."""
    svc = KnowledgeLibraryService()
    return await svc.save_progress(
        user_id=current_user["id"],
        resource_id=body.resource_id,
        status=body.status,
        progress_pct=body.progress_pct,
    )


@router.post("/rate")
@limiter.limit("10/minute")
async def rate_resource(
    request: Request,
    body: RateResourceRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Rate a knowledge resource."""
    svc = KnowledgeLibraryService()
    return await svc.rate_resource(
        user_id=current_user["id"],
        resource_id=body.resource_id,
        rating=body.rating,
    )


# ── Recommendations ──────────────────────────────────────────────────

@router.get("/recommendations")
@limiter.limit("30/minute")
async def get_recommendations(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get personalized resource recommendations."""
    svc = KnowledgeLibraryService()
    return await svc.get_recommendations(current_user["id"])


@router.post("/recommendations/generate")
@limiter.limit("5/minute")
async def generate_recommendations(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Re-generate recommendations based on current skill gaps and goals."""
    svc = KnowledgeLibraryService()
    return await svc.generate_recommendations(current_user["id"])


@router.post("/recommendations/{rec_id}/dismiss")
@limiter.limit("30/minute")
async def dismiss_recommendation(
    request: Request,
    rec_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Dismiss a recommendation."""
    svc = KnowledgeLibraryService()
    await svc.dismiss_recommendation(current_user["id"], rec_id)
    return {"ok": True}
