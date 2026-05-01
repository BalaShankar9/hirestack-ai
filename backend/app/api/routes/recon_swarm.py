"""Recon Swarm v2 API — /api/recon-swarm/*."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from ai_engine.agents.sub_agents.recon_swarm import (
    ReconSwarmCoordinator,
    ReconSwarmRequest,
    get_default_cache,
)
from app.core.security import limiter

logger = structlog.get_logger("hirestack.recon_swarm")
router = APIRouter()


@router.post("/profile")
@limiter.limit("3/hour")
async def profile(request: Request, body: ReconSwarmRequest) -> dict:
    try:
        report = await ReconSwarmCoordinator().run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "recon_swarm_profile",
        company=body.company,
        cache_hit=report.cache_hit,
        completeness=report.intel.profile_completeness,
        providers=len(report.provider_results),
    )
    return {"report": report.model_dump()}


@router.get("/cache-stats")
@limiter.limit("30/hour")
async def cache_stats(request: Request) -> dict:
    return await get_default_cache().stats()
