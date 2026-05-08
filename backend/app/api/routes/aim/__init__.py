"""
AIM (Assignment Intelligence Module) API surface.

Mounted at /api/aim by app/api/routes/__init__.py.

Endpoints (all require Bearer auth via get_current_user):

  POST   /assignments                       create assignment
  GET    /assignments                       list user's assignments
  GET    /assignments/{id}                  read one
  DELETE /assignments/{id}                  delete one
  POST   /assignments/{id}/documents        attach a document (text body)
  POST   /assignments/{id}/documents/upload upload a file (multipart)
  GET    /assignments/{id}/documents        list documents
  POST   /assignments/{id}/sources          create source card
  GET    /assignments/{id}/sources          list source cards
  POST   /assignments/{id}/analyze          run Parser+Recon (returns plan or clarifications)
  GET    /assignments/{id}/analysis         read latest analysis
  GET    /assignments/{id}/sections         list sections
  POST   /sections/{section_id}/generate    writer\u2192reviewer loop, returns final + history
  POST   /sections/{section_id}/generate-stream SSE
  POST   /sections/{section_id}/fix         diagnostic fix-my-section
  GET    /sections/{section_id}/outputs     output version history
  POST   /assignments/{id}/predict-grade    aggregate grade prediction
  GET    /assignments/{id}/evaluations      evaluation history
  GET    /usage                             current month aim_usage row
"""
from fastapi import APIRouter

from app.api.routes.aim.assignments import router as assignments_router
from app.api.routes.aim.documents import router as documents_router
from app.api.routes.aim.sources import router as sources_router
from app.api.routes.aim.analysis import router as analysis_router
from app.api.routes.aim.sections import router as sections_router
from app.api.routes.aim.evaluations import router as evaluations_router
from app.api.routes.aim.usage import router as usage_router
from app.api.routes.aim.deadline import router as deadline_router

router = APIRouter()
router.include_router(assignments_router)
router.include_router(documents_router)
router.include_router(sources_router)
router.include_router(analysis_router)
router.include_router(sections_router)
router.include_router(evaluations_router)
router.include_router(usage_router)
router.include_router(deadline_router)
