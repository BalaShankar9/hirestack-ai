"""
HireStack AI - API Routes
Aggregates all API route modules
"""
from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.resume import router as resume_router
from app.api.routes.profile import router as profile_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.benchmark import router as benchmark_router
from app.api.routes.gaps import router as gaps_router
from app.api.routes.consultant import router as consultant_router
from app.api.routes.builder import router as builder_router
from app.api.routes.export import router as export_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.generate import router as generate_router
from app.api.routes.ats import router as ats_router
from app.api.routes.interview import router as interview_router
from app.api.routes.salary import router as salary_router
from app.api.routes.career import router as career_router
from app.api.routes.learning import router as learning_router
from app.api.routes.variants import router as variants_router
from app.api.routes.job_sync import router as job_sync_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.review import router as review_router
from app.api.routes.orgs import router as orgs_router
from app.api.routes.billing import router as billing_router
from app.api.routes.candidates import router as candidates_router
from app.api.routes.feedback import router as feedback_router

router = APIRouter()

# Core
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(resume_router, prefix="/resume", tags=["Resume"])
router.include_router(profile_router, prefix="/profile", tags=["Profile"])
router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
router.include_router(benchmark_router, prefix="/benchmark", tags=["Benchmark"])
router.include_router(gaps_router, prefix="/gaps", tags=["Gap Analysis"])
router.include_router(consultant_router, prefix="/consultant", tags=["Career Consultant"])
router.include_router(builder_router, prefix="/builder", tags=["Document Builder"])
router.include_router(export_router, prefix="/export", tags=["Export"])
router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
router.include_router(generate_router, prefix="/generate", tags=["AI Generation"])

# Features
router.include_router(ats_router, prefix="/ats", tags=["ATS Scanner"])
router.include_router(interview_router, prefix="/interview", tags=["Interview"])
router.include_router(salary_router, prefix="/salary", tags=["Salary Coach"])
router.include_router(career_router, prefix="/career", tags=["Career Analytics"])
router.include_router(learning_router, prefix="/learning", tags=["Learning"])
router.include_router(variants_router, prefix="/variants", tags=["Document Variants"])
router.include_router(job_sync_router, prefix="/job-sync", tags=["Job Sync"])
router.include_router(api_keys_router, prefix="/api-keys", tags=["API Keys"])
router.include_router(review_router, prefix="/review", tags=["Review"])
router.include_router(orgs_router, prefix="/orgs", tags=["Organizations"])
router.include_router(billing_router, prefix="/billing", tags=["Billing"])
router.include_router(candidates_router, prefix="/candidates", tags=["Candidates"])
router.include_router(feedback_router, prefix="/feedback", tags=["Feedback & Outcomes"])
