"""
Collaborative Review routes - Shareable links, comments, and AI feedback (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.review import ReviewService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


async def _verify_session_access(service: ReviewService, session_id: str, share_token: str):
    """Verify the share_token is valid and corresponds to this session."""
    session = await service.get_session_by_token(share_token)
    if not session or session.get("id") != session_id:
        raise HTTPException(status_code=403, detail="Invalid or expired share token")


class CreateReviewRequest(BaseModel):
    application_id: str = Field(..., min_length=1, max_length=100)
    document_type: str = Field("cv", max_length=50)
    reviewer_name: str = Field("", max_length=200)
    expires_hours: int = Field(168, ge=1, le=720)


class AddCommentRequest(BaseModel):
    reviewer_name: str = Field("Anonymous", max_length=200)
    comment_text: str = Field(..., max_length=10_000)
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    section: str = Field("", max_length=200)


@router.post("/create")
@limiter.limit("10/minute")
async def create_review_session(
    request: Request,
    body: CreateReviewRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a shareable review session."""
    service = ReviewService()
    return await service.create_review_session(
        user_id=current_user["id"],
        application_id=body.application_id,
        document_type=body.document_type,
        reviewer_name=body.reviewer_name,
        expires_hours=body.expires_hours,
    )


@router.get("/token/{share_token}")
@limiter.limit("30/minute")
async def get_session_by_token(request: Request, share_token: str):
    """Get a review session by share token (public endpoint)."""
    if len(share_token) > 500:
        raise HTTPException(status_code=422, detail="Invalid share token")
    service = ReviewService()
    session = await service.get_session_by_token(share_token)
    if not session:
        raise HTTPException(status_code=404, detail="Review session not found or expired")
    return session


@router.post("/{session_id}/comment")
@limiter.limit("10/minute")
async def add_comment(
    request: Request,
    session_id: str,
    body: AddCommentRequest,
    share_token: str = Query(..., max_length=500),
):
    """Add a comment to a review session (requires valid share token)."""
    _validate_uuid(session_id, "session_id")
    service = ReviewService()
    await _verify_session_access(service, session_id, share_token)
    return await service.add_comment(
        session_id=session_id,
        reviewer_name=body.reviewer_name,
        comment_text=body.comment_text,
        selection_start=body.selection_start,
        selection_end=body.selection_end,
        section=body.section,
    )


@router.get("/{session_id}/comments")
@limiter.limit("30/minute")
async def get_comments(
    request: Request,
    session_id: str,
    share_token: str = Query(..., max_length=500),
):
    """Get all comments for a review session (requires valid share token)."""
    _validate_uuid(session_id, "session_id")
    service = ReviewService()
    await _verify_session_access(service, session_id, share_token)
    return await service.get_comments(session_id)


@router.get("/{session_id}/summary")
@limiter.limit("10/minute")
async def summarize_feedback(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """AI-powered summary of all review feedback."""
    _validate_uuid(session_id, "session_id")
    service = ReviewService()
    return await service.summarize_feedback(session_id, current_user["id"])


@router.get("/")
@limiter.limit("30/minute")
async def get_user_sessions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get all review sessions for the current user."""
    service = ReviewService()
    return await service.get_user_sessions(current_user["id"])


@router.delete("/{session_id}")
@limiter.limit("20/minute")
async def deactivate_session(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Deactivate a review session."""
    _validate_uuid(session_id, "session_id")
    service = ReviewService()
    success = await service.deactivate_session(session_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deactivated"}
