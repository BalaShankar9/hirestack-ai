"""
HireStack AI - FastAPI Application
Main entry point for the backend API
"""
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
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
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

    ai_configured = False
    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        ai_configured = True
    elif settings.ai_provider == "openai" and settings.openai_api_key:
        ai_configured = True
    elif settings.ai_provider == "ollama":
        ai_configured = True  # Ollama doesn't need an API key
    if not ai_configured:
        logger.warning(
            "No AI provider configured — generation endpoints will fail",
            provider=settings.ai_provider,
        )

    try:
        from app.api.routes.generate import recover_inflight_generation_jobs

        recovered = await recover_inflight_generation_jobs()
        if recovered:
            logger.info("Recovered inflight generation jobs", count=recovered)
    except Exception as e:
        logger.warning("Failed to recover inflight generation jobs", error=str(e))
    yield
    # Shutdown
    logger.info("Shutting down HireStack AI")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered career intelligence and job application platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc",  # Always available for API reference
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
    allow_headers=["Authorization", "Content-Type", "X-Org-Id", "X-API-Key", "Accept", "Origin"],
)


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
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred",
            "error": str(exc) if settings.debug else "Internal server error",
        },
    )


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    supabase_status = {"ok": False}
    try:
        client = get_supabase()
        result = client.table("users").select("id").limit(1).execute()
        supabase_status = {"ok": True}
    except Exception as e:
        supabase_status = {"ok": False, "error": str(e)}

    # Check AI provider
    ai_status = {"provider": getattr(settings, "ai_provider", "unknown"), "ok": False}
    try:
        if getattr(settings, "ai_provider", "") == "ollama":
            import httpx
            r = httpx.get("http://localhost:11434/api/tags", timeout=2)
            ai_status["ok"] = r.status_code == 200
        elif getattr(settings, "gemini_api_key", ""):
            ai_status["ok"] = True
            ai_status["provider"] = "gemini"
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "supabase": {
            "url": settings.supabase_url,
            "database": supabase_status,
        },
        "ai": ai_status,
        "sentry": bool(settings.sentry_dsn),
    }


# Include API routes
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
