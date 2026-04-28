"""S1-F11: Health and readiness probes.

Three endpoints:
  - GET /livez            cheap liveness probe (event loop only)
  - GET /healthz/ready    fast readiness probe (Supabase + Redis)
  - GET /health           full diagnostic snapshot (DB, AI, Redis,
                          breakers, model health, metrics, queue)

The full /health endpoint exposes detailed internals only when
``settings.debug`` is true or ``settings.environment`` is not
production — otherwise it returns just status + version, suitable
for public exposure.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import get_supabase

router = APIRouter()


def _json_safe(value: Any) -> Any:
    """Best-effort conversion for values that may include test mocks."""
    try:
        json.dumps(value)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return str(value)


async def _check_supabase(timeout_s: float = 5.0) -> Dict[str, Any]:
    try:
        client = get_supabase()
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.table("users").select("id").limit(1).execute()
            ),
            timeout=timeout_s,
        )
        return {"connected": True}
    except Exception as e:
        _detail = (
            str(e)
            if (settings.debug or settings.environment != "production")
            else "unavailable"
        )
        return {"connected": False, "error": _detail}


async def _check_redis(timeout_s: float = 2.0) -> Dict[str, Any]:
    try:
        from app.core.cache import get_redis

        r = get_redis()
        if r is None:
            # Redis is optional — falling back to in-mem cache is OK.
            return {"connected": False, "fallback": "in_memory"}
        await asyncio.wait_for(asyncio.to_thread(r.ping), timeout=timeout_s)
        return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}


@router.get("/livez", tags=["Health"], include_in_schema=False)
async def liveness_probe():
    """Lightweight liveness probe.

    Returns 200 iff the event loop is responsive. NEVER touches DB,
    Redis, or external APIs. Designed for kubelet liveness probes —
    use /healthz/ready for readiness.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "alive", "version": settings.app_version},
    )


@router.get("/healthz/ready", tags=["Health"], include_in_schema=False)
async def readiness_probe():
    """Fast readiness probe for orchestrator readiness gating.

    Returns 200 only when Supabase is reachable. Redis is optional
    (in-memory fallback is acceptable). Does NOT include AI provider,
    breaker state, model health, or metrics — keep it cheap.
    """
    supabase_status = await _check_supabase(timeout_s=2.0)
    redis_status = await _check_redis(timeout_s=1.0)
    ready = supabase_status.get("connected", False)
    code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=code,
        content={
            "status": "ready" if ready else "not_ready",
            "supabase": supabase_status,
            "redis": redis_status,
        },
    )


@router.get("/health", tags=["Health"])
async def health_check():
    """Full health snapshot — returns operational status.

    Internal diagnostics (circuit breakers, model health, metrics,
    queue depth) are only returned when DEBUG=true or
    ENVIRONMENT != production.
    """
    supabase_status = await _check_supabase()

    # AI provider key presence is the cheapest proxy without an API call.
    _ai_key_ok = bool(getattr(settings, "gemini_api_key", "")) or getattr(
        settings, "gemini_use_vertexai", False
    )
    ai_status = {"provider": "gemini", "ok": _ai_key_ok}

    redis_status = await _check_redis()

    breaker_status: Dict[str, Any] = {}
    try:
        from app.core.circuit_breaker import _breakers

        for name, breaker in _breakers.items():
            breaker_status[name] = {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
            }
    except Exception:
        pass

    model_health: Dict[str, Any] = {}
    try:
        from ai_engine.model_router import get_model_health

        model_health = get_model_health()
    except Exception:
        pass

    metrics_summary: Dict[str, Any] = {}
    try:
        from app.core.metrics import MetricsCollector

        metrics_summary = MetricsCollector.get().get_stats()
    except Exception:
        pass

    queue_info: Dict[str, Any] = {}
    try:
        from app.core.queue import queue_depth

        depth = queue_depth()
        queue_info = {
            "pending": depth,
            "backend": "redis_streams" if depth >= 0 else "in_process",
        }
    except Exception:
        queue_info = {"backend": "in_process"}

    _supabase_ok = supabase_status.get("connected", False)
    _ai_degraded_in_prod = (
        settings.environment == "production" and not ai_status.get("ok", False)
    )
    degraded = not _supabase_ok or _ai_degraded_in_prod
    overall = "degraded" if degraded else "healthy"
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if degraded
        else status.HTTP_200_OK
    )

    content: Dict[str, Any] = {"status": overall, "version": settings.app_version}

    _show_internals = settings.debug or settings.environment != "production"
    if _show_internals:
        content.update(
            {
                "environment": settings.environment,
                "supabase": supabase_status,
                "ai": {
                    "provider": ai_status.get("provider", "unknown"),
                    "ok": ai_status.get("ok", False),
                },
                "redis": redis_status,
                "circuit_breakers": breaker_status,
                "model_health": model_health,
                "metrics": metrics_summary,
                "queue": queue_info,
            }
        )

    return JSONResponse(status_code=code, content=_json_safe(content))


__all__ = ["router"]
