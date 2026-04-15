"""
HireStack AI - FastAPI Application
Main entry point for the backend API
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for ai_engine imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from urllib.parse import urlparse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_supabase, get_supabase
from app.core.tracing import RequestIDMiddleware, AccessLogMiddleware, MaxBodySizeMiddleware, request_id_var
from app.api.routes import router as api_router

# ── Sentry Error Monitoring ────────────────────────────────────────────
if settings.sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1 if settings.environment == "production" else 1.0,
            profiles_sample_rate=0.1,
            send_default_pii=False,
        )
    except ImportError:
        pass

# Configure structured logging
def _add_request_id(logger_instance, method_name, event_dict):
    """Structlog processor: inject X-Request-ID from context var."""
    rid = request_id_var.get("")
    if rid:
        event_dict["request_id"] = rid
    return event_dict


structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_request_id,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Import the shared per-user limiter from security module
from app.core.security import limiter  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler."""
    # Startup
    logger.info("Starting HireStack AI", version=settings.app_version)
    init_supabase()
    logger.info("Supabase client initialized")

    # Eagerly initialize Redis cache connection
    try:
        from app.core.database import get_redis
        r = get_redis()
        if r:
            logger.info("Redis cache ready")
            # Pre-create the consumer group for the job queue so workers
            # can connect immediately.
            try:
                from app.core.queue import _ensure_group
                _ensure_group(r)
                logger.info("Redis Streams consumer group ready")
            except Exception as grp_err:
                logger.warning("Queue consumer group init skipped", error=str(grp_err)[:200])
        else:
            logger.info("Redis unavailable — using in-memory cache fallback")
    except Exception as redis_err:
        logger.warning("Redis init failed", error=str(redis_err)[:200])

    # Validate critical configuration
    _is_prod = settings.environment == "production"
    if not settings.supabase_url or settings.supabase_url == "https://placeholder.supabase.co":
        msg = "SUPABASE_URL is not configured — database operations will fail"
        if _is_prod:
            raise RuntimeError(msg)
        logger.warning(msg)
    if not settings.supabase_service_role_key:
        msg = "SUPABASE_SERVICE_ROLE_KEY is not configured — backend DB access will fail"
        if _is_prod:
            raise RuntimeError(msg)
        logger.warning(msg)

    ai_configured = bool(settings.gemini_api_key) or settings.gemini_use_vertexai
    if not ai_configured:
        msg = (
            "Gemini is not configured — generation endpoints will fail. "
            "Set GEMINI_API_KEY or enable GEMINI_USE_VERTEXAI."
        )
        if _is_prod:
            raise RuntimeError(msg)
        logger.warning(msg)

    try:
        from app.api.routes.generate import recover_inflight_generation_jobs

        recovered = await asyncio.wait_for(recover_inflight_generation_jobs(), timeout=15)
        if recovered:
            logger.info("Recovered inflight generation jobs", count=recovered)
    except asyncio.TimeoutError:
        logger.warning("recover_inflight_jobs timed out after 15s — skipping")
    except Exception as e:
        logger.warning("Failed to recover inflight generation jobs", error=str(e))

    # Hydrate cost optimizer quality observations from DB
    try:
        from ai_engine.model_router import hydrate_quality_observations
        loaded = hydrate_quality_observations()
        if loaded:
            logger.info("Quality observations hydrated", count=loaded)
    except Exception as e:
        logger.debug("Quality observations hydration skipped", error=str(e))

    # Seed the document type catalog (idempotent)
    try:
        from app.services.document_catalog import ensure_catalog_seeded
        from app.core.database import TABLES
        await ensure_catalog_seeded(get_supabase(), TABLES)
        logger.info("Document type catalog seeded")
    except Exception as e:
        logger.warning("Document catalog seeding failed", error=str(e)[:200])

    # Sweep for orphaned modules stuck in 'generating' with no active job
    try:
        from app.api.routes.generate import cleanup_orphaned_generating_modules

        orphans = await asyncio.wait_for(cleanup_orphaned_generating_modules(), timeout=15)
        if orphans:
            logger.info("Cleaned up orphaned generating modules", count=orphans)
    except asyncio.TimeoutError:
        logger.warning("orphan module cleanup timed out after 15s — skipping")
    except Exception as e:
        logger.warning("Failed to clean up orphaned modules", error=str(e))

    # Check PipelineRuntime availability — fallback paths lack catalog integration
    try:
        from app.api.routes.generate import _RUNTIME_AVAILABLE
        if not _RUNTIME_AVAILABLE:
            logger.critical(
                "PipelineRuntime not available — fallback execution paths lack "
                "catalog learning, company intel integration, and doc pack planning. "
                "Ensure pipeline_runtime.py and its dependencies are importable."
            )
    except Exception:
        pass

    # Start periodic stale job cleanup (every 10 minutes)
    _stale_cleanup_task = asyncio.create_task(_periodic_stale_job_cleanup())

    # Register SIGTERM handler for graceful shutdown (Railway sends SIGTERM)
    import signal

    _shutting_down = asyncio.Event()
    app.state._shutting_down = _shutting_down

    def _handle_sigterm(*_: object) -> None:
        logger.info("SIGTERM received — beginning graceful shutdown")
        _shutting_down.set()

    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except (NotImplementedError, RuntimeError):
        pass  # Windows / no running loop

    yield

    # Shutdown — wait briefly for in-flight requests to finish
    logger.info("Draining in-flight requests (up to 10s)…")
    await asyncio.sleep(2)  # give a short grace period for inflight work

    # Cancel active generation tasks gracefully
    try:
        from app.api.routes.generate import _ACTIVE_GENERATION_TASKS
        if _ACTIVE_GENERATION_TASKS:
            logger.info("Cancelling active generation tasks", count=len(_ACTIVE_GENERATION_TASKS))
            for task_id, task in list(_ACTIVE_GENERATION_TASKS.items()):
                task.cancel()
            # Wait for cancellation to propagate
            await asyncio.gather(
                *_ACTIVE_GENERATION_TASKS.values(),
                return_exceptions=True,
            )
            logger.info("All generation tasks drained")
    except Exception as e:
        logger.warning("Generation task drain failed", error=str(e))

    _stale_cleanup_task.cancel()
    try:
        await _stale_cleanup_task
    except asyncio.CancelledError:
        pass
    # Release database client
    from app.core.database import close_supabase
    close_supabase()
    logger.info("Shutting down HireStack AI — goodbye")


async def _periodic_stale_job_cleanup() -> None:
    """Background task that sweeps for stale generation jobs every 10 minutes."""
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            from app.api.routes.generate import cleanup_stale_generation_jobs
            cleaned = await asyncio.wait_for(cleanup_stale_generation_jobs(), timeout=30)
            if cleaned:
                logger.info("Stale job cleanup completed", cleaned_count=cleaned)
            # Also sweep orphaned modules with no active job
            from app.api.routes.generate import cleanup_orphaned_generating_modules
            orphans = await asyncio.wait_for(cleanup_orphaned_generating_modules(), timeout=30)
            if orphans:
                logger.info("Orphaned module cleanup completed", cleaned_count=orphans)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Stale job cleanup error", error=str(e))


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered career intelligence and job application platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS helpers
def _split_origins(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _with_localhost_aliases(origins: list[str]) -> list[str]:
    """Add localhost/127.0.0.1 aliases for the same scheme+port."""
    out: set[str] = set()
    for origin in origins:
        try:
            parsed = urlparse(origin)
            if not parsed.scheme or not parsed.hostname:
                continue
            host = parsed.hostname
            port = parsed.port
            if host in ("localhost", "127.0.0.1") and port is not None:
                other = "127.0.0.1" if host == "localhost" else "localhost"
                out.add(f"{parsed.scheme}://{other}:{port}")
        except Exception:
            continue
    return list(out)


# CORS middleware
base_origins = list(dict.fromkeys(settings.cors_origins + _split_origins(settings.allowed_origins)))
extra_origins = _with_localhost_aliases(base_origins)
allowed_origins = list(dict.fromkeys(base_origins + extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Org-Id", "X-API-Key", "Accept", "Origin", "X-Request-ID"],
)

# Request-ID tracing (runs BEFORE security headers so the ID is available everywhere)
from app.core.security import SecurityHeadersMiddleware  # noqa: E402

app.add_middleware(RequestIDMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    rid = request_id_var.get("")
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        request_id=rid,
        exc_info=True,
    )
    body: dict = {
        "detail": "An unexpected error occurred",
        "error": "Internal server error",
    }
    if rid:
        body["request_id"] = rid
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body,
    )


# Health check — unauthenticated, so only expose operational status, not internals
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint — returns operational status.

    Internal diagnostics (circuit breakers, model health, metrics, queue depth)
    are only returned when DEBUG=true or ENVIRONMENT != production.
    """
    supabase_status = {"connected": False}
    try:
        client = get_supabase()
        await asyncio.wait_for(
            asyncio.to_thread(lambda: client.table("users").select("id").limit(1).execute()),
            timeout=5,
        )
        supabase_status = {"connected": True}
    except Exception as e:
        _detail = str(e) if (settings.debug or settings.environment != "production") else "unavailable"
        supabase_status = {"connected": False, "error": _detail}

    # Check AI provider (Gemini only)
    ai_status = {"provider": "gemini", "ok": bool(getattr(settings, "gemini_api_key", "")) or getattr(settings, "gemini_use_vertexai", False)}

    # Redis cache health
    redis_status = {"connected": False}
    try:
        from app.core.database import get_redis
        r = get_redis()
        if r is not None:
            await asyncio.wait_for(asyncio.to_thread(r.ping), timeout=2)
            redis_status = {"connected": True}
    except Exception as e:
        redis_status = {"connected": False, "error": str(e)[:200]}

    # Circuit breaker state
    breaker_status = {}
    try:
        from app.core.circuit_breaker import _breakers
        for name, breaker in _breakers.items():
            breaker_status[name] = {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
            }
    except Exception:
        pass

    # Model health (cascade failover router)
    model_health = {}
    try:
        from ai_engine.model_router import get_model_health
        model_health = get_model_health()
    except Exception:
        pass

    # Pipeline metrics summary
    metrics_summary = {}
    try:
        from app.core.metrics import MetricsCollector
        metrics_summary = MetricsCollector.get().get_stats()
    except Exception:
        pass

    # Job queue depth
    queue_info = {}
    try:
        from app.core.queue import queue_depth
        depth = queue_depth()
        queue_info = {"pending": depth, "backend": "redis_streams" if depth >= 0 else "in_process"}
    except Exception:
        queue_info = {"backend": "in_process"}

    # Determine overall health – Supabase down = degraded
    degraded = not supabase_status.get("connected", False)
    overall = "degraded" if degraded else "healthy"
    code = status.HTTP_503_SERVICE_UNAVAILABLE if degraded else status.HTTP_200_OK

    # Base response — safe for public exposure
    content: dict = {
        "status": overall,
        "version": settings.app_version,
    }

    # Detailed internals only in non-production or debug mode
    _show_internals = settings.debug or settings.environment != "production"
    if _show_internals:
        content.update({
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
        })

    return JSONResponse(
        status_code=code,
        content=content,
    )


# ── Frontend error collector ───────────────────────────────────────────
from pydantic import BaseModel, Field  # noqa: E402
from typing import List  # noqa: E402


# ── Prometheus-compatible metrics endpoint ─────────────────────────────

@app.get("/metrics", tags=["Observability"], include_in_schema=False)
async def prometheus_metrics():
    """Expose pipeline metrics in Prometheus text exposition format.

    Provides gauges and counters for pipeline performance, circuit breakers,
    model health, and queue depth — compatible with Prometheus scrapers,
    Grafana Cloud, and Railway metrics.
    """
    lines: list[str] = []

    # Pipeline run metrics
    try:
        from app.core.metrics import MetricsCollector
        stats = MetricsCollector.get().get_stats()

        active = stats.get("active_jobs", 0)
        lines.append("# HELP hirestack_active_jobs Number of in-flight generation jobs")
        lines.append("# TYPE hirestack_active_jobs gauge")
        lines.append(f"hirestack_active_jobs {active}")

        failovers = stats.get("model_failovers_total", 0)
        lines.append("# HELP hirestack_model_failovers_total Cumulative model cascade failovers")
        lines.append("# TYPE hirestack_model_failovers_total counter")
        lines.append(f"hirestack_model_failovers_total {failovers}")

        for pipeline_name, pstats in stats.get("pipelines", {}).items():
            safe_name = pipeline_name.replace("-", "_").replace(" ", "_")
            count = pstats.get("count", 0)
            success_rate = pstats.get("success_rate", 0)
            p50 = pstats.get("duration_p50_ms", 0)
            p95 = pstats.get("duration_p95_ms", 0)

            lines.append(f'hirestack_pipeline_runs_total{{pipeline="{safe_name}"}} {count}')
            lines.append(f'hirestack_pipeline_success_rate{{pipeline="{safe_name}"}} {success_rate}')
            lines.append(f'hirestack_pipeline_duration_p50_ms{{pipeline="{safe_name}"}} {p50}')
            lines.append(f'hirestack_pipeline_duration_p95_ms{{pipeline="{safe_name}"}} {p95}')

        for error_class, ecount in stats.get("error_counts", {}).items():
            safe_class = error_class.replace('"', '\\"')
            lines.append(f'hirestack_errors_total{{error_class="{safe_class}"}} {ecount}')
    except Exception:
        pass

    # Circuit breaker states
    try:
        from app.core.circuit_breaker import _breakers
        lines.append("# HELP hirestack_circuit_breaker_state Circuit breaker state (0=closed, 1=half_open, 2=open)")
        lines.append("# TYPE hirestack_circuit_breaker_state gauge")
        state_map = {"closed": 0, "half_open": 1, "open": 2}
        for name, breaker in _breakers.items():
            state_val = state_map.get(breaker.state.value, -1)
            safe_name = name.replace("-", "_").replace(" ", "_")
            lines.append(f'hirestack_circuit_breaker_state{{breaker="{safe_name}"}} {state_val}')
            lines.append(f'hirestack_circuit_breaker_failures{{breaker="{safe_name}"}} {breaker.failure_count}')
    except Exception:
        pass

    # Redis / queue depth
    try:
        from app.core.queue import queue_depth
        depth = queue_depth()
        lines.append("# HELP hirestack_queue_depth Pending jobs in Redis Streams queue")
        lines.append("# TYPE hirestack_queue_depth gauge")
        lines.append(f"hirestack_queue_depth {max(0, depth)}")
    except Exception:
        pass

    from starlette.responses import Response
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


class _FEError(BaseModel):
    message: str = Field(..., max_length=500)
    stack: str | None = Field(None, max_length=2000)
    componentStack: str | None = Field(None, max_length=1000)
    url: str = Field("", max_length=500)
    timestamp: str = Field("", max_length=40)
    userAgent: str = Field("", max_length=300)


class _FEErrorBatch(BaseModel):
    errors: List[_FEError] = Field(..., max_length=20)


@app.post("/api/frontend-errors", status_code=204, tags=["Observability"])
async def collect_frontend_errors(batch: _FEErrorBatch) -> None:
    """Receive client-side error reports and log them server-side."""
    for err in batch.errors:
        logger.warning(
            "frontend_error",
            message=err.message,
            url=err.url,
            timestamp=err.timestamp,
            stack=err.stack,
            component_stack=err.componentStack,
        )


# Include API routes
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
