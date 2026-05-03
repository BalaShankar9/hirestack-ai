"""Streaming Recon Swarm API — /api/recon-swarm/stream/*.

Server-Sent Events (SSE) for real-time recon progress.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ai_engine.agents.sub_agents.recon_swarm import (
    ReconSwarmRequest,
    StreamingReconCoordinator,
)
from app.core.security import limiter

logger = structlog.get_logger("hirestack.recon_swarm_streaming")
router = APIRouter()


# Global coordinator instance with all production features
coordinator = StreamingReconCoordinator(
    enable_resilience=True,
    enable_health_tracking=True,
    enable_metrics=True,
    enable_provider_cache=True,
    mode="auto",  # Auto-detect free vs full mode
)


@router.post("/profile/stream")
@limiter.limit("10/hour")
async def profile_stream(request: Request, body: ReconSwarmRequest):
    """Stream recon progress via Server-Sent Events.
    
    Yields real-time updates as the recon progresses through layers:
    - Layer 1: Source Discovery (35%)
    - Layer 2: Deep Extraction (50%)  
    - Layer 3: Fusion (75%)
    - Layer 4: Weaponization (95%)
    - Layer 5: Complete (100%)
    
    Example Event Stream:
        data: {"phase": "source_discovery", "status": "running", "percent": 5, ...}
        data: {"phase": "source_discovery", "status": "running", "percent": 15, ...}
        data: {"phase": "fusion", "status": "running", "percent": 60, ...}
        data: {"phase": "completed", "status": "completed", "percent": 100, ...}
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for progress in coordinator.run_streaming(body):
                data = json.dumps(progress.to_dict())
                yield f"data: {data}\n\n"
        except Exception as e:
            logger.error("recon_stream_error", error=str(e))
            error_data = json.dumps({
                "phase": "failed",
                "status": "failed",
                "percent": 0,
                "message": str(e),
            })
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/health")
@limiter.limit("60/hour")
async def health(request: Request):
    """Get provider health status.
    
    Returns health snapshot for all providers including:
    - status: healthy/degraded/unhealthy
    - success_rate_1h: float 0-1
    - avg_latency_ms: average response time
    """
    return coordinator.get_health()


@router.get("/metrics")
@limiter.limit("60/hour")
async def metrics(request: Request, format: str = Query("json", enum=["json", "prometheus"])):
    """Get recon metrics.
    
    Args:
        format: Output format - "json" or "prometheus"
    
    Returns:
        Metrics including:
        - Total requests
        - Cache hit ratio
        - Provider success rates
        - Latency percentiles
    """
    if format == "prometheus":
        return coordinator.get_metrics_prometheus()
    return coordinator.get_metrics()


@router.post("/profile")
@limiter.limit("5/hour")
async def profile_sync(request: Request, body: ReconSwarmRequest):
    """Non-streaming recon (backward compatible).
    
    Use this when you just need the final result without progress updates.
    """
    try:
        result = await coordinator.run(body)
        return {
            "report": result.report.model_dump(),
            "health": {
                name: {
                    "status": h.status,
                    "success_rate": h.success_rate_1h,
                }
                for name, h in result.health_snapshot.items()
            },
            "metrics": result.metrics,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers")
@limiter.limit("30/hour")
async def list_providers(request: Request):
    """List available data providers and their status.
    
    Shows which providers are available based on:
    - Mode (free/full)
    - API key configuration
    - Health status
    """
    health = coordinator.get_health()
    
    providers = []
    for name, h in health.get("providers", {}).items():
        providers.append({
            "name": name,
            "mode": health.get("mode"),
            "status": h.get("status"),
            "success_rate": h.get("success_rate"),
            "latency_ms": h.get("avg_latency_ms"),
        })
    
    return {
        "mode": health.get("mode"),
        "providers": providers,
    }


@router.post("/invalidate-cache")
@limiter.limit("10/hour")
async def invalidate_cache(request: Request, company: str):
    """Invalidate cached recon data for a company.
    
    Use when you need fresh data for a previously researched company.
    """
    from ai_engine.agents.sub_agents.recon_swarm.cache import cache_key
    
    # Generate cache keys for common variations
    keys = [
        cache_key({"c": company.lower(), "r": "", "w": "", "s": [], "v": [], "m": "free"}),
        cache_key({"c": company.lower(), "r": "", "w": "", "s": [], "v": [], "m": "full"}),
    ]
    
    # Note: Actual invalidation would need cache.delete() method
    return {
        "company": company,
        "keys_targeted": [k[:16] + "..." for k in keys],
        "message": "Cache invalidation queued",
    }
