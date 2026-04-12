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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_supabase, get_supabase
from app.core.tracing import RequestIDMiddleware, request_id_var
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

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler."""
    # Startup
    logger.info("Starting HireStack AI", version=settings.app_version)
    init_supabase()
    logger.info("Supabase client initialized")

    # Validate critical configuration
    if not settings.supabase_url or settings.supabase_url == "https://placeholder.supabase.co":
        logger.warning("SUPABASE_URL is not configured — database operations will fail")
    if not settings.supabase_service_role_key:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY is not configured — backend DB access will fail")

    ai_configured = bool(settings.gemini_api_key) or settings.gemini_use_vertexai
    if not ai_configured:
        logger.warning(
            "Gemini is not configured — generation endpoints will fail. "
            "Set GEMINI_API_KEY or enable GEMINI_USE_VERTEXAI.",
        )

    try:
        from app.api.routes.generate import recover_inflight_generation_jobs

        recovered = await recover_inflight_generation_jobs()
        if recovered:
            logger.info("Recovered inflight generation jobs", count=recovered)
    except Exception as e:
        logger.warning("Failed to recover inflight generation jobs", error=str(e))

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

    yield

    # Shutdown
    _stale_cleanup_task.cancel()
    try:
        await _stale_cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down HireStack AI")


async def _periodic_stale_job_cleanup() -> None:
    """Background task that sweeps for stale generation jobs every 10 minutes."""
    while True:
        try:
            await asyncio.sleep(600)  # 10 minutes
            from app.api.routes.generate import cleanup_stale_generation_jobs
            cleaned = await cleanup_stale_generation_jobs()
            if cleaned:
                logger.info("Stale job cleanup completed", cleaned_count=cleaned)
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
        "error": str(exc) if settings.debug else "Internal server error",
    }
    if rid:
        body["request_id"] = rid
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body,
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    supabase_status = {"ok": False}
    try:
        client = get_supabase()
        client.table("users").select("id").limit(1).execute()
        supabase_status = {"ok": True}
    except Exception as e:
        supabase_status = {"ok": False, "error": str(e)}

    # Check AI provider (Gemini only)
    ai_status = {"provider": "gemini", "ok": bool(getattr(settings, "gemini_api_key", "")) or getattr(settings, "gemini_use_vertexai", False)}

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

    # Pipeline metrics summary
    metrics_summary = {}
    try:
        from app.core.metrics import MetricsCollector
        metrics_summary = MetricsCollector.get().get_stats()
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "supabase": {
            "connected": supabase_status.get("ok", False),
        },
        "ai": {
            "provider": ai_status.get("provider", "unknown"),
            "ok": ai_status.get("ok", False),
        },
        "sentry": bool(settings.sentry_dsn),
        "circuit_breakers": breaker_status,
        "metrics": metrics_summary,
    }


# Include API routes
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
