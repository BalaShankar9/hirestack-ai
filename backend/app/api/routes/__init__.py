"""
HireStack AI - API Routes
Aggregates all API route modules
"""
from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.resume import router as resume_router

router = APIRouter()

# Include auth routes (other routes to be added after Firestore migration)
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(resume_router, prefix="/resume", tags=["Resume"])

# TODO: Add these back after updating services for Firestore
# from app.api.routes.profile import router as profile_router
# from app.api.routes.jobs import router as jobs_router
# from app.api.routes.benchmark import router as benchmark_router
# from app.api.routes.gaps import router as gaps_router
# from app.api.routes.consultant import router as consultant_router
# from app.api.routes.builder import router as builder_router
# from app.api.routes.export import router as export_router
# from app.api.routes.analytics import router as analytics_router
# router.include_router(profile_router, prefix="/profile", tags=["Profile"])
# router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
# router.include_router(benchmark_router, prefix="/benchmark", tags=["Benchmark"])
# router.include_router(gaps_router, prefix="/gaps", tags=["Gap Analysis"])
# router.include_router(consultant_router, prefix="/consultant", tags=["Career Consultant"])
# router.include_router(builder_router, prefix="/builder", tags=["Document Builder"])
# router.include_router(export_router, prefix="/export", tags=["Export"])
# router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
