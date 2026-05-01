"""Portfolio Site Generator API — /api/portfolio/*."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from ai_engine.agents.portfolio import (
    PortfolioInput,
    SiteGenerator,
)
from app.core.security import limiter

logger = structlog.get_logger("hirestack.portfolio")
router = APIRouter()


@router.post("/generate")
@limiter.limit("5/hour")
async def generate(request: Request, body: PortfolioInput) -> dict:
    try:
        site = await SiteGenerator().generate(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "portfolio_generate",
        theme=body.theme,
        projects=len(body.projects),
        experience=len(body.experience),
    )
    return {"site": site.model_dump()}
