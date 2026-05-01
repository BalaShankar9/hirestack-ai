"""LinkedIn Profile Optimizer API — /api/linkedin/*."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.agents.linkedin import LinkedInOptimizer, LinkedInProfile
from app.core.security import limiter

logger = structlog.get_logger("hirestack.linkedin")
router = APIRouter()


class OptimizeRequest(BaseModel):
    profile: LinkedInProfile
    target_role: str = Field(..., min_length=2, max_length=200)
    include_headline_ab: bool = True
    headline_variant_count: int = Field(3, ge=1, le=5)


class HeadlineRequest(BaseModel):
    profile: LinkedInProfile
    target_role: str = Field(..., min_length=2, max_length=200)
    n: int = Field(3, ge=1, le=5)


@router.post("/optimize")
@limiter.limit("10/hour")
async def optimize(request: Request, body: OptimizeRequest) -> dict:
    optimizer = LinkedInOptimizer()
    try:
        report = await optimizer.optimize(
            body.profile,
            body.target_role,
            include_headline_ab=body.include_headline_ab,
            headline_variant_count=body.headline_variant_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("linkedin_optimize_failed", error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="optimization failed") from exc
    return report.model_dump()


@router.post("/headline-ab")
@limiter.limit("20/hour")
async def headline_ab(request: Request, body: HeadlineRequest) -> dict:
    optimizer = LinkedInOptimizer()
    try:
        variants = await optimizer.headline_ab(body.profile, body.target_role, n=body.n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"variants": [v.model_dump() for v in variants]}
