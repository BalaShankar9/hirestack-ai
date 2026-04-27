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
from .cv_variants import router as cv_variants_router

router = APIRouter()
router.include_router(sync_router)
router.include_router(planned_router)
router.include_router(stream_router)
router.include_router(jobs_router)
router.include_router(document_router)
router.include_router(cv_variants_router)

# ── Re-exports for backward compatibility ──
# main.py imports these
from .helpers import _RUNTIME_AVAILABLE  # noqa: E402, F401
from .jobs import (  # noqa: E402, F401
    recover_inflight_generation_jobs,
    cleanup_stale_generation_jobs,
    cleanup_orphaned_generating_modules,
)

# Tests and other modules import these
from .helpers import (  # noqa: E402, F401
    _extract_pipeline_html,
    _classify_ai_error,
    _extract_retry_after_seconds,
    _validate_pipeline_input,
    _format_response,
    _quality_score_from_scores,
    _build_evidence_summary,
    _sse,
    _agent_sse,
    PIPELINE_TIMEOUT,
)
from .schemas import (  # noqa: E402, F401
    GenerateDocumentRequest,
    PipelineRequest,
    GenerationJobRequest,
    RetryModulesRequest,
)
from .jobs import (  # noqa: E402, F401
    _fetch_job_and_application,
    _normalize_requested_modules,
    _default_module_states,
    _merge_module_states,
    _module_has_content,
    _finalize_orphaned_job,
    _mark_application_generation_finished,
    _ACTIVE_GENERATION_TASKS,
    _CAMEL_TO_SNAKE,
    _SNAKE_TO_CAMEL,
    _IDENTITY_KEYS,
    _DEFAULT_REQUESTED_MODULES,
    create_generation_job,
    get_generation_job_status,
    retry_generation_modules,
    replay_generation_job,
)
