"""
HireStack AI - FastAPI Application
Main entry point for the backend API
"""
import sys
import os
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

from app.core.config import settings
from app.core.database import init_firebase, get_db
from app.api.routes import router as api_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler."""
    # Startup
    logger.info("Starting HireStack AI", version=settings.app_version)
    init_firebase()
    logger.info("Firebase initialized")

    yield

    # Shutdown
    logger.info("Shutting down HireStack AI")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered career intelligence and job application platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + [settings.allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors with detailed messages."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """Handle unexpected errors."""
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred",
            "error": str(exc) if settings.debug else "Internal server error"
        }
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    firestore_status = {"ok": True}
    try:
        db = get_db()
        # A lightweight call that fails fast if Firestore isn't provisioned.
        db.collection("_health").document("ping").get(timeout=2)
    except Exception as e:
        firestore_status = {"ok": False, "error": str(e)}

    storage_status = {"ok": None}
    try:
        from google.cloud import storage as gcstorage  # type: ignore
        from google.oauth2 import service_account  # type: ignore

        cred_path = settings.firebase_credentials_path
        resolved_cred_path = None
        if cred_path:
            resolved_cred_path = cred_path
            if not os.path.isabs(resolved_cred_path):
                resolved_cred_path = os.path.join(os.getcwd(), resolved_cred_path)

        gcp_creds = None
        if resolved_cred_path and os.path.exists(resolved_cred_path):
            gcp_creds = service_account.Credentials.from_service_account_file(resolved_cred_path)

        client = gcstorage.Client(project=settings.firebase_project_id, credentials=gcp_creds)

        candidates = []
        if getattr(settings, "firebase_storage_bucket", None):
            candidates.append(settings.firebase_storage_bucket)
        candidates.extend(
            [
                f"{settings.firebase_project_id}.appspot.com",
                f"{settings.firebase_project_id}.firebasestorage.app",
            ]
        )

        seen = set()
        found = None
        last_err = None
        for b in candidates:
            if not b or b in seen:
                continue
            seen.add(b)
            try:
                client.get_bucket(b)
                found = b
                break
            except Exception as e:
                last_err = str(e)

        if found:
            storage_status = {"ok": True, "bucket": found}
        else:
            storage_status = {
                "ok": False,
                "bucketCandidates": [b for b in candidates if b],
                "error": last_err or "Storage bucket not found.",
            }
    except Exception as e:
        storage_status = {"ok": False, "error": str(e)}

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "firebase": {
            "projectId": settings.firebase_project_id,
            "firestore": firestore_status,
            "storage": storage_status,
        },
    }


# Include API routes
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
