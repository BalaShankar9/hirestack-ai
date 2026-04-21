"""
Interview Simulator routes
"""
from typing import Dict, Any

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field

from app.services.interview import InterviewService
from app.api.deps import get_current_user, check_billing_limit
from app.api.response import success_response
import structlog

logger = structlog.get_logger()

router = APIRouter()


class CreateSessionRequest(BaseModel):
    job_title: str
    company: str = ""
    jd_text: str = ""
    profile_summary: str = ""
    skills_summary: str = ""
    difficulty: str = "intermediate"
    interview_type: str = "mixed"
    question_count: int = Field(default=10, ge=1, le=20)


class SubmitAnswerRequest(BaseModel):
    question_id: str
    answer: str


@router.post("/sessions")
@limiter.limit("30/minute")
async def create_session(
    request: Request,
    req: CreateSessionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user
),
):
    """Create a new interview session."""
    await check_billing_limit("ai_calls", current_user)
    if not req.job_title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_title is required",
        )
    service = InterviewService()
    try:
        session = await service.create_session(
            user_id=current_user["id"],
            job_title=req.job_title,
            company=req.company,
            jd_text=req.jd_text,
            profile_summary=req.profile_summary,
            skills_summary=req.skills_summary,
            difficulty=req.difficulty,
            interview_type=req.interview_type,
            question_count=req.question_count,
        )
        return success_response(session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("create_session_error", error=str(e), user_id=current_user["id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


@router.post("/sessions/{session_id}/answers")
@limiter.limit("30/minute")
async def submit_answer(
    request: Request,
    session_id: str,
    req: SubmitAnswerRequest,
    current_user: Dict[str, Any] = Depends(get_current_user
),
):
    """Submit an answer for evaluation."""
    if not req.answer.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="answer is required",
        )
    service = InterviewService()
    try:
        evaluation = await service.submit_answer(
            session_id=session_id,
            user_id=current_user["id"],
            question_id=req.question_id,
            answer=req.answer,
        )
        # Merge question_id and the candidate's own text into the response
        # so the frontend has everything it needs to render the review card
        # without a second round-trip.
        payload = dict(evaluation) if isinstance(evaluation, dict) else {"raw": evaluation}
        payload.setdefault("question_id", req.question_id)
        payload.setdefault("answer_text", req.answer)
        return success_response(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("submit_answer_error", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


@router.post("/sessions/{session_id}/complete")
@limiter.limit("30/minute")
async def complete_session(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark session as completed."""
    service = InterviewService()
    try:
        session = await service.complete_session(session_id, current_user["id"])
        # Expose the canonical overall_score field so the frontend doesn't
        # have to know about the legacy average_score column name.
        if isinstance(session, dict) and "overall_score" not in session:
            session = {**session, "overall_score": session.get("average_score", 0)}
        return success_response(session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("complete_session_error", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


@router.get("/sessions")
@limiter.limit("30/minute")
async def list_sessions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's interview sessions."""
    service = InterviewService()
    return await service.get_user_sessions(current_user["id"])


@router.get("/sessions/{session_id}")
@limiter.limit("30/minute")
async def get_session(
    request: Request,
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific interview session."""
    service = InterviewService()
    session = await service.get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found",
        )
    return session
