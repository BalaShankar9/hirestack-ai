"""
Interview Simulator routes - AI mock interviews (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.interview import InterviewService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class StartSessionRequest(BaseModel):
    job_title: str = Field(..., max_length=500)
    company: str = Field("", max_length=500)
    jd_text: str = Field("", max_length=100_000)
    interview_type: str = Field("mixed", max_length=50)
    difficulty: str = Field("medium", max_length=50)
    question_count: int = Field(8, ge=1, le=30)
    application_id: Optional[str] = Field(None, max_length=100)
    profile_summary: str = Field("", max_length=50_000)
    gap_summary: str = Field("", max_length=50_000)


class SubmitAnswerRequest(BaseModel):
    question_index: int = Field(..., ge=0, le=50)
    answer_text: str = Field(..., max_length=50_000)
    duration_seconds: int = Field(0, ge=0, le=7200)


@router.post("/start")
@limiter.limit("5/minute")
async def start_session(
    request: Request,
    body: StartSessionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Start a new interview practice session."""
    service = InterviewService()
    try:
        return await service.start_session(
            user_id=current_user["id"],
            job_title=body.job_title,
            company=body.company,
            jd_text=body.jd_text,
            interview_type=body.interview_type,
            difficulty=body.difficulty,
            question_count=body.question_count,
            application_id=body.application_id,
            profile_summary=body.profile_summary,
            gap_summary=body.gap_summary,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to start interview session. Please try again.")


@router.post("/{session_id}/answer")
@limiter.limit("30/minute")
async def submit_answer(
    request: Request,
    session_id: str,
    body: SubmitAnswerRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Submit and evaluate an answer for a question."""
    _validate_uuid(session_id, "session_id")
    service = InterviewService()
    try:
        return await service.submit_answer(
            user_id=current_user["id"],
            session_id=session_id,
            question_index=body.question_index,
            answer_text=body.answer_text,
            duration_seconds=body.duration_seconds,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session or question index.")
    except Exception:
        raise HTTPException(status_code=500, detail="Answer evaluation failed. Please try again.")


@router.post("/{session_id}/complete")
@limiter.limit("10/minute")
async def complete_session(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Complete a session and get overall feedback."""
    _validate_uuid(session_id, "session_id")
    service = InterviewService()
    try:
        return await service.complete_session(current_user["id"], session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Session not found or already completed.")


@router.get("/{session_id}")
@limiter.limit("30/minute")
async def get_session(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a session with its answers."""
    _validate_uuid(session_id, "session_id")
    service = InterviewService()
    session = await service.get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/")
@limiter.limit("30/minute")
async def get_sessions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get recent interview sessions."""
    service = InterviewService()
    return await service.get_user_sessions(current_user["id"])
