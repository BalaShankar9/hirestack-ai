"""Executive Video Pitch API — /api/video-pitch/*."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from ai_engine.agents.video_pitch import (
    PitchOrchestrator,
    VideoPitchInput,
)
from app.core.security import limiter

logger = structlog.get_logger("hirestack.video_pitch")
router = APIRouter()


@router.post("/create")
@limiter.limit("3/hour")
async def create(request: Request, body: VideoPitchInput) -> dict:
    try:
        pkg = await PitchOrchestrator().create(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "video_pitch_create",
        provider=pkg.manifest.provider,
        status=pkg.manifest.status,
        duration=body.duration_seconds,
        style=body.avatar_style,
    )
    return {"package": pkg.model_dump()}
