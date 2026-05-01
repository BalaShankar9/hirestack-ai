"""
Interview Simulator API — /api/interview/sim.

Endpoints:
    POST /api/interview/sim/start   → Start session, return first question.
    POST /api/interview/sim/answer  → Submit answer, return score + next q.
    POST /api/interview/sim/finish  → Finalize, return SessionReport.

Sessions are kept in a process-local in-memory dict for this slice
(persistence comes in a later wave). Sessions auto-expire after 1h.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.agents.interview_sim import InterviewSimulator
from ai_engine.agents.interview_sim.schemas import InterviewSession
from app.core.security import limiter

logger = structlog.get_logger("hirestack.interview.sim")
router = APIRouter()


# Process-local session store ────────────────────────────────────────
_SESSIONS: Dict[str, tuple[float, InterviewSession]] = {}
_TTL_S = 60 * 60  # 1 hour


def _gc_sessions() -> None:
    now = time.time()
    expired = [sid for sid, (ts, _) in _SESSIONS.items() if now - ts > _TTL_S]
    for sid in expired:
        _SESSIONS.pop(sid, None)


def _store(session: InterviewSession) -> None:
    _gc_sessions()
    _SESSIONS[session.session_id] = (time.time(), session)


def _load(session_id: str) -> InterviewSession:
    record = _SESSIONS.get(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="session not found or expired")
    _, session = record
    return session


# Request models ─────────────────────────────────────────────────────
class StartRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=200)
    jd: Optional[str] = Field(None, max_length=20_000)
    resume: Optional[str] = Field(None, max_length=20_000)
    question_count: int = Field(10, ge=5, le=15)
    audience_hint: Optional[str] = Field(None, max_length=200)
    with_audio: bool = False


class AnswerRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    question_id: str = Field(..., min_length=8, max_length=80)
    answer: str = Field(..., min_length=1, max_length=20_000)


class FinishRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)


# Routes ──────────────────────────────────────────────────────────────
@router.post("/sim/start")
@limiter.limit("10/hour")
async def sim_start(request: Request, body: StartRequest) -> dict:
    try:
        sim = InterviewSimulator()
        session = await sim.start_session(
            role=body.role, jd=body.jd, resume=body.resume,
            question_count=body.question_count,
            audience_hint=body.audience_hint, with_audio=body.with_audio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("interview_sim_start_failed", error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="failed to start session") from exc
    _store(session)
    first = session.questions[0] if session.questions else None
    return {
        "session_id": session.session_id,
        "role": session.role,
        "question_count": len(session.questions),
        "first_question": first.model_dump() if first else None,
    }


@router.post("/sim/answer")
@limiter.limit("60/hour")
async def sim_answer(request: Request, body: AnswerRequest) -> dict:
    sim = InterviewSimulator()
    session = _load(body.session_id)
    try:
        turn = sim.submit_answer(session, question_id=body.question_id, answer=body.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    next_q = sim.next_question(session)
    _store(session)  # refresh timestamp
    return {
        "turn": turn.model_dump(),
        "next_question": next_q.model_dump() if next_q else None,
        "completed": next_q is None,
    }


@router.post("/sim/finish")
@limiter.limit("20/hour")
async def sim_finish(request: Request, body: FinishRequest) -> dict:
    sim = InterviewSimulator()
    session = _load(body.session_id)
    report = sim.finalize(session)
    _store(session)
    return report.model_dump()
