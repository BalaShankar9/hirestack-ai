"""
Unified AI Generation Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Package split from the original monolith for maintainability.
"""
from fastapi import APIRouter

from .sync_pipeline import router as sync_router
from .planned import router as planned_router
from .stream import router as stream_router
from .jobs import router as jobs_router
from .document import router as document_router

router = APIRouter()
router.include_router(sync_router)
router.include_router(planned_router)
router.include_router(stream_router)
router.include_router(jobs_router)
router.include_router(document_router)

# ── Re-exports for backward compatibility ──
# main.py imports these
from .helpers import _RUNTIME_AVAILABLE  # noqa: F401
from .jobs import (  # noqa: F401
    recover_inflight_generation_jobs,
    cleanup_stale_generation_jobs,
    cleanup_orphaned_generating_modules,
)

# Tests import these
from .helpers import _extract_pipeline_html  # noqa: F401
from .schemas import GenerateDocumentRequest  # noqa: F401
from .jobs import (  # noqa: F401
    _fetch_job_and_application,
    _normalize_requested_modules,
    _default_module_states,
    _merge_module_states,
    _module_has_content,
    _run_generation_job_inner,
    _finalize_orphaned_job,
    _CAMEL_TO_SNAKE,
    _SNAKE_TO_CAMEL,
    _IDENTITY_KEYS,
    _DEFAULT_REQUESTED_MODULES,
)
