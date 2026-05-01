"""Networking Outreach API — /api/networking/*."""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.agents.networking import (
    EmailWriter,
    OutreachContext,
    SequencePlanner,
)
from app.core.security import limiter

logger = structlog.get_logger("hirestack.networking")
router = APIRouter()


class DraftRequest(BaseModel):
    ctx: OutreachContext
    ask_type: Optional[str] = None
    tone: str = Field("warm", min_length=2, max_length=40)


class SequenceRequest(BaseModel):
    ctx: OutreachContext
    follow_up_count: int = Field(2, ge=0, le=4)


@router.post("/draft")
@limiter.limit("20/hour")
async def draft(request: Request, body: DraftRequest) -> dict:
    try:
        d = await EmailWriter().write(body.ctx, ask_type=body.ask_type, tone=body.tone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("networking_draft", ask_type=body.ask_type, tone=body.tone)
    return {"draft": d.model_dump()}


@router.post("/sequence")
@limiter.limit("10/hour")
async def sequence(request: Request, body: SequenceRequest) -> dict:
    try:
        seq = await SequencePlanner().plan(
            body.ctx, follow_up_count=body.follow_up_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "networking_sequence",
        ask_type=body.ctx.ask_type,
        follow_ups=body.follow_up_count,
    )
    return {"sequence": seq.model_dump()}
