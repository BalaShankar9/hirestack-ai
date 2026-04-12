"""DB-backed generation jobs: endpoints, infrastructure, runtime, and cleanup."""
import asyncio
import traceback
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, validate_uuid, check_billing_limit
from app.core.security import limiter

from .schemas import GenerationJobRequest, RetryModulesRequest, ALLOWED_JOB_MODULES
from .helpers import (
    _RUNTIME_AVAILABLE,
    _AGENT_PIPELINES_AVAILABLE,
    _classify_ai_error,
    _extract_pipeline_html,
    _extract_keywords_from_jd,
    _build_evidence_summary,
    _format_response,
    _sanitize_output_html,
    _sse,
    _PIPELINE_NAMES,
    _STAGE_ORDER,
    logger,
)

try:
    from .helpers import (
        _PipelineRuntime, _RuntimeConfig, _ExecutionMode, _DatabaseSink,
    )
except ImportError:
    pass

try:
    from .helpers import (
        _WorkflowEventStore, _reconstruct_state,
        _get_completed_stages, _is_safely_resumable,
    )
except ImportError:
    pass

try:
    from .helpers import (
        cv_generation_pipeline, cover_letter_pipeline,
        personal_statement_pipeline, portfolio_pipeline,
        PipelineResult,
    )
except ImportError:
    pass

router = APIRouter()

_ACTIVE_GENERATION_TASKS: Dict[str, asyncio.Task] = {}
_JOB_TOTAL_STEPS = 7
_DEFAULT_REQUESTED_MODULES = [
    "benchmark",
    "gaps",
    "learningPlan",
    "cv",
    "coverLetter",
    "personalStatement",
    "portfolio",
    "scorecard",
]

# Bidirectional key mapping: snake_case ↔ camelCase
_SNAKE_TO_CAMEL = {
    "cover_letter": "coverLetter",
    "personal_statement": "personalStatement",
    "learning_plan": "learningPlan",
    "gap_analysis": "gaps",
}
_CAMEL_TO_SNAKE = {v: k for k, v in _SNAKE_TO_CAMEL.items()}
# Keys that are identical in both formats
_IDENTITY_KEYS = {"benchmark", "cv", "portfolio", "scorecard", "gaps"}


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _default_module_states() -> Dict[str, Dict[str, Any]]:
    return {
        "benchmark": {"state": "idle"},
        "gaps": {"state": "idle"},
        "learningPlan": {"state": "idle"},
        "cv": {"state": "idle"},
        "coverLetter": {"state": "idle"},
        "personalStatement": {"state": "idle"},
        "portfolio": {"state": "idle"},
        "scorecard": {"state": "idle"},
    }


def _merge_module_states(existing_modules: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    modules: Dict[str, Any] = _default_module_states()
    if isinstance(existing_modules, dict):
        modules.update(existing_modules)
    return modules


def _normalize_requested_modules(requested_modules: Optional[List[str]]) -> List[str]:
    """Normalize module keys to camelCase (internal canonical form).
    Accepts both snake_case (from /jobs endpoint) and camelCase (from frontend).
    """
    if not requested_modules:
        return list(_DEFAULT_REQUESTED_MODULES)

    normalized = []
    seen = set()
    for mod in requested_modules:
        # Convert snake_case → camelCase if needed
        key = _SNAKE_TO_CAMEL.get(mod, mod)
        if key in seen:
            continue
        # Accept if it's a known default module
        if key in _DEFAULT_REQUESTED_MODULES:
            normalized.append(key)
            seen.add(key)

    return normalized or list(_DEFAULT_REQUESTED_MODULES)


def _module_has_content(application_row: Dict[str, Any], module_key: str) -> bool:
    if module_key == "benchmark":
        return bool(application_row.get("benchmark"))
    if module_key == "gaps":
        return bool(application_row.get("gaps"))
    if module_key == "learningPlan":
        return bool(application_row.get("learning_plan"))
    if module_key == "cv":
        return bool(str(application_row.get("cv_html") or "").strip())
    if module_key == "coverLetter":
        return bool(str(application_row.get("cover_letter_html") or "").strip())
    if module_key == "personalStatement":
        return bool(str(application_row.get("personal_statement_html") or "").strip())
    if module_key == "portfolio":
        return bool(str(application_row.get("portfolio_html") or "").strip())
    if module_key == "scorecard":
        return bool(application_row.get("scorecard") or application_row.get("scores"))
    return False


async def _persist_application_patch(sb: Any, tables: Dict[str, str], application_id: str, patch: Dict[str, Any]) -> None:
    if not patch:
        return
    await asyncio.to_thread(
        lambda: sb.table(tables["applications"])
        .update(patch)
        .eq("id", application_id)
        .execute()
    )


async def _ensure_generation_job_schema_ready(sb: Any, tables: Dict[str, str]) -> None:
    try:
        await asyncio.to_thread(
            lambda: sb.table(tables["generation_jobs"])
            .select("id,current_agent,completed_steps,total_steps,active_sources_count")
            .limit(1)
            .execute()
        )
        await asyncio.to_thread(
            lambda: sb.table(tables["generation_job_events"])
            .select("id")
            .limit(1)
            .execute()
        )
        await asyncio.to_thread(
            lambda: sb.table(tables["applications"])
            .select("id,discovered_documents,generated_documents,benchmark_documents,document_strategy,company_intel")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("generation_job_schema_not_ready", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Generation jobs schema not ready. Apply the latest database migrations and retry.",
        ) from exc


async def _set_application_modules_generating(
    sb: Any,
    tables: Dict[str, str],
    application_id: str,
    existing_modules: Optional[Dict[str, Any]],
    requested_modules: List[str],
) -> None:
    timestamp = _now_ms()
    modules = _merge_module_states(existing_modules)
    for module_key in requested_modules:
        modules[module_key] = {"state": "generating", "updatedAt": timestamp}

    await _persist_application_patch(
        sb,
        tables,
        application_id,
        {"modules": modules},
    )


async def _mark_application_generation_finished(
    sb: Any,
    tables: Dict[str, str],
    application_id: str,
    application_row: Optional[Dict[str, Any]],
    requested_modules: List[str],
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    timestamp = _now_ms()

    # Always read fresh application state to avoid stale-snapshot overwrites.
    # The caller may pass application_row=None to force a fresh read.
    fresh_row = application_row
    if fresh_row is None:
        try:
            resp = await asyncio.to_thread(
                lambda: sb.table(tables["applications"])
                .select("id,modules,cv_html,cover_letter_html,personal_statement_html,portfolio_html,benchmark,gaps,learning_plan,scores,scorecard")
                .eq("id", application_id)
                .maybe_single()
                .execute()
            )
            fresh_row = resp.data if resp else None
        except Exception as fetch_err:
            logger.warning("stream.fresh_row_fetch_failed", error=str(fetch_err)[:200])
            fresh_row = None
    if fresh_row is None:
        fresh_row = {}

    modules = _merge_module_states(fresh_row.get("modules"))

    for module_key in requested_modules:
        current_state = (modules.get(module_key) or {}).get("state", "idle")
        # Never overwrite a "ready" module from a concurrent successful job
        # with an error/idle from a different job that failed.
        if current_state == "ready" and status in ("failed", "cancelled"):
            continue
        if status == "cancelled":
            next_state = "ready" if _module_has_content(fresh_row, module_key) else "idle"
            modules[module_key] = {"state": next_state, "updatedAt": timestamp}
        elif status == "failed":
            modules[module_key] = {
                "state": "error",
                "updatedAt": timestamp,
                "error": error_message or "Generation failed.",
            }
        else:
            modules[module_key] = {"state": "ready", "updatedAt": timestamp}

    await _persist_application_patch(
        sb,
        tables,
        application_id,
        {"modules": modules},
    )


async def _sync_generation_tasks(
    sb: Any,
    tables: Dict[str, str],
    *,
    user_id: str,
    application_id: str,
    gaps: Optional[Dict[str, Any]],
    learning_plan: Optional[Dict[str, Any]],
) -> None:
    task_resp = await asyncio.to_thread(
        lambda: sb.table(tables["tasks"])
        .select("id,source,title,status")
        .eq("user_id", user_id)
        .eq("application_id", application_id)
        .limit(500)
        .execute()
    )

    existing_by_key: Dict[str, Dict[str, Any]] = {}
    for row in task_resp.data or []:
        source = str(row.get("source") or "")
        title = str(row.get("title") or "")
        if source not in {"gaps", "learningPlan"} or not title:
            continue
        existing_by_key[f"{source}:{title}"] = row

    candidates: List[Dict[str, Any]] = []

    missing_keywords = [
        str(keyword).strip()
        for keyword in (gaps or {}).get("missingKeywords", [])
        if str(keyword).strip()
    ]
    for index, keyword in enumerate(missing_keywords[:8]):
        candidates.append(
            {
                "source": "gaps",
                "title": f"Add proof for {keyword}",
                "description": (
                    f"Create one concrete artifact (project, certification, or link) that demonstrates {keyword}, "
                    "then attach it in Evidence."
                ),
                "detail": f"Missing keyword: {keyword}",
                "why": (
                    "This keyword appears in the JD signal. Proof-backed keywords improve match and credibility."
                ),
                "status": "todo",
                "priority": "high" if index < 3 else "medium",
            }
        )

    for week in (learning_plan or {}).get("plan", [])[:3]:
        if not isinstance(week, dict):
            continue
        week_num = week.get("week") if isinstance(week.get("week"), int) else None
        theme = str(week.get("theme") or "Learning sprint")
        for task_text in week.get("tasks", [])[:2]:
            text = str(task_text).strip()
            if not text:
                continue
            title_core = f"{text[:77]}…" if len(text) > 80 else text
            candidates.append(
                {
                    "source": "learningPlan",
                    "title": f"Week {week_num}: {title_core}" if week_num else title_core,
                    "description": text,
                    "detail": theme,
                    "why": "Each learning sprint should produce a proof artifact you can attach to your application.",
                    "status": "todo",
                    "priority": "medium",
                }
            )

    seen: set[str] = set()
    for candidate in candidates:
        key = f"{candidate['source']}:{candidate['title']}"
        if key in seen:
            continue
        seen.add(key)

        existing = existing_by_key.get(key)
        if existing:
            existing_status = str(existing.get("status") or "todo")
            if existing_status in {"done", "skipped"}:
                continue
            await asyncio.to_thread(
                lambda existing_id=str(existing.get("id") or ""): sb.table(tables["tasks"])
                .update(
                    {
                        "description": candidate["description"],
                        "detail": candidate["detail"],
                        "why": candidate["why"],
                        "status": existing_status,
                        "priority": candidate["priority"],
                    }
                )
                .eq("id", existing_id)
                .execute()
            )
            continue

        await asyncio.to_thread(
            lambda row={
                "user_id": user_id,
                "application_id": application_id,
                "source": candidate["source"],
                "title": candidate["title"],
                "description": candidate["description"],
                "detail": candidate["detail"],
                "why": candidate["why"],
                "status": candidate["status"],
                "priority": candidate["priority"],
            }: sb.table(tables["tasks"])
            .insert(row)
            .execute()
        )


async def _persist_generation_result_to_application(
    sb: Any,
    tables: Dict[str, str],
    *,
    application_row: Dict[str, Any],
    requested_modules: List[str],
    result: Dict[str, Any],
    user_id: str,
) -> None:
    application_id = str(application_row["id"])
    timestamp = _now_ms()
    modules = _merge_module_states(application_row.get("modules"))
    patch: Dict[str, Any] = {}
    requested = set(requested_modules)

    if "benchmark" in requested and result.get("benchmark"):
        benchmark = dict(result["benchmark"])
        benchmark["createdAt"] = timestamp
        patch["benchmark"] = benchmark

    if "gaps" in requested and result.get("gaps"):
        patch["gaps"] = result["gaps"]

    if "learningPlan" in requested and result.get("learningPlan"):
        patch["learning_plan"] = result["learningPlan"]

    if "cv" in requested and result.get("cvHtml"):
        patch["cv_html"] = result["cvHtml"]

    if "coverLetter" in requested and result.get("coverLetterHtml"):
        patch["cover_letter_html"] = result["coverLetterHtml"]

    if "personalStatement" in requested and result.get("personalStatementHtml"):
        patch["personal_statement_html"] = result["personalStatementHtml"]

    if "portfolio" in requested and result.get("portfolioHtml"):
        patch["portfolio_html"] = result["portfolioHtml"]

    if "scorecard" in requested:
        if result.get("validation"):
            patch["validation"] = result["validation"]
        if result.get("scorecard"):
            scorecard = dict(result["scorecard"])
            scorecard["updatedAt"] = timestamp
            patch["scorecard"] = scorecard
        if result.get("scores"):
            patch["scores"] = result["scores"]

    if result.get("discoveredDocuments") is not None:
        patch["discovered_documents"] = result["discoveredDocuments"]
    if result.get("generatedDocuments") is not None:
        patch["generated_documents"] = result["generatedDocuments"]
    if result.get("benchmarkDocuments") is not None:
        patch["benchmark_documents"] = result["benchmarkDocuments"]
    if result.get("documentStrategy") is not None:
        patch["document_strategy"] = result["documentStrategy"]

    company_intel = result.get("companyIntel")
    if company_intel is None:
        company_intel = ((result.get("meta") or {}).get("company_intel"))
    if company_intel is not None:
        patch["company_intel"] = company_intel

    for module_key in requested_modules:
        modules[module_key] = {"state": "ready", "updatedAt": timestamp}
    patch["modules"] = modules

    await _persist_application_patch(sb, tables, application_id, patch)

    if "gaps" in requested or "learningPlan" in requested:
        try:
            await _sync_generation_tasks(
                sb,
                tables,
                user_id=user_id,
                application_id=application_id,
                gaps=result.get("gaps") if "gaps" in requested else None,
                learning_plan=result.get("learningPlan") if "learningPlan" in requested else None,
            )
        except Exception as task_err:
            logger.warning("job_runner.task_sync_failed", application_id=application_id, error=str(task_err))


def _phase_to_agent_name(phase: str) -> str:
    mapping = {
        "initializing": "recon",
        "recon": "recon",
        "recon_done": "recon",
        "profiling": "atlas",
        "profiling_done": "atlas",
        "gap_analysis": "cipher",
        "gap_analysis_done": "cipher",
        "documents": "quill",
        "documents_done": "quill",
        "portfolio": "forge",
        "portfolio_done": "forge",
        "validation": "sentinel",
        "validation_done": "sentinel",
        "formatting": "nova",
        "complete": "nova",
    }
    return mapping.get(phase, phase or "pipeline")


async def _persist_generation_job_update(sb: Any, tables: Dict[str, str], job_id: str, patch: Dict[str, Any]) -> None:
    if not patch:
        return
    await asyncio.to_thread(
        lambda: sb.table(tables["generation_jobs"])
        .update(patch)
        .eq("id", job_id)
        .execute()
    )


async def _persist_generation_job_event(
    sb: Any,
    tables: Dict[str, str],
    *,
    job_id: str,
    user_id: str,
    application_id: str,
    sequence_no: int,
    event_name: str,
    payload: Dict[str, Any],
) -> None:
    stage = payload.get("stage") or payload.get("phase")
    row = {
        "job_id": job_id,
        "user_id": user_id,
        "application_id": application_id,
        "sequence_no": sequence_no,
        "event_name": event_name,
        "agent_name": payload.get("agent") or payload.get("pipeline_name") or _phase_to_agent_name(str(stage or "")),
        "stage": stage,
        "status": payload.get("status"),
        "message": payload.get("message") or "",
        "source": payload.get("source"),
        "url": payload.get("url"),
        "latency_ms": payload.get("latency_ms"),
        "payload": payload,
    }
    await asyncio.to_thread(
        lambda: sb.table(tables["generation_job_events"])
        .insert(row)
        .execute()
    )


async def _finalize_orphaned_job(
    job_id: str,
    *,
    status: str = "failed",
    error_message: str = "Generation failed unexpectedly. Please try again.",
) -> None:
    """Best-effort DB finalization for a job whose owning task is gone.

    Reads the current job row to check if it is already terminal.
    If not, marks it terminal and reconciles application module states.
    This is the single authoritative "catch-all" that prevents orphaned
    running/queued jobs.
    """
    try:
        from app.core.database import get_supabase, TABLES
        sb = get_supabase()
        # Read current job state — avoid overwriting a terminal status
        job_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .select("id,status,application_id,requested_modules,user_id")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        job = job_resp.data if job_resp else None
        if not job:
            return
        if job.get("status") in {"succeeded", "failed", "cancelled"}:
            return  # already terminal — nothing to do

        # Mark job terminal
        await _persist_generation_job_update(
            sb, TABLES, job_id,
            {
                "status": status,
                "error_message": error_message,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        # Reconcile module states from fresh DB row
        app_id = job.get("application_id", "")
        requested_modules = _normalize_requested_modules(job.get("requested_modules"))
        if app_id and requested_modules:
            await _mark_application_generation_finished(
                sb, TABLES, app_id, None, requested_modules,
                status=status, error_message=error_message,
            )
    except Exception as e:
        logger.error("finalize_orphaned_job_failed", job_id=job_id, error=str(e))


async def _run_generation_job(job_id: str, user_id: str) -> None:  # noqa: C901
    """Run a generation job with a hard 30-minute timeout."""
    try:
        await asyncio.wait_for(
            _run_generation_job_inner(job_id, user_id),
            timeout=1800,  # 30 minutes
        )
    except asyncio.TimeoutError:
        logger.error("job_runner.timeout", job_id=job_id)
        await _finalize_orphaned_job(
            job_id,
            status="failed",
            error_message="Generation timed out after 30 minutes. Please try again.",
        )
    except asyncio.CancelledError:
        logger.warning("job_runner.cancelled_externally", job_id=job_id)
        await _finalize_orphaned_job(
            job_id,
            status="cancelled",
            error_message="Generation was cancelled.",
        )
    except Exception as e:
        logger.error("job_runner.unexpected_outer_error", job_id=job_id, error=str(e))
        await _finalize_orphaned_job(
            job_id,
            status="failed",
            error_message="Generation failed unexpectedly. Please try again.",
        )
    finally:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)


async def _fetch_job_and_application(
    job_id: str, user_id: str
) -> tuple[Any, dict, dict, str, List[str]] | None:
    """
    Shared helper: fetch generation job + its parent application.

    Returns (sb, job, app_data, application_id, requested_modules) or None
    if the job/application can't be found.
    """
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not job_resp.data:
        logger.warning("job_fetch.job_not_found", job_id=job_id)
        return None

    job = job_resp.data[0]
    application_id = job.get("application_id", "")
    requested_modules = _normalize_requested_modules(job.get("requested_modules"))

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not app_resp.data:
        logger.warning("job_fetch.app_not_found", job_id=job_id, application_id=application_id)
        return None

    return sb, job, app_resp.data[0], application_id, requested_modules


async def _run_generation_job_inner(job_id: str, user_id: str) -> None:  # noqa: C901
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    # NOTE: Using .limit(1) instead of .maybe_single() because the
    # 'message' column name in generation_jobs conflicts with
    # postgrest-py's error response parsing, causing a spurious 204.
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not job_resp.data:
        logger.warning("job_runner.job_not_found", job_id=job_id)
        # Mark as failed so it doesn't stay queued forever
        try:
            await _persist_generation_job_update(
                sb, TABLES, job_id,
                {
                    "status": "failed",
                    "error_message": "Generation job record not found.",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as persist_err:
            logger.warning("job_runner.missing_job_persist_failed", job_id=job_id, error=str(persist_err)[:200])
        return

    job = job_resp.data[0]
    app_id = job["application_id"]
    requested_modules = _normalize_requested_modules(job.get("requested_modules"))

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", app_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "failed",
                "error_message": "Application not found",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return

    application_row = app_resp.data
    confirmed_facts = application_row.get("confirmed_facts") or {}
    job_title = confirmed_facts.get("jobTitle") or confirmed_facts.get("job_title") or ""
    company_name = confirmed_facts.get("company") or ""
    jd_text_val = confirmed_facts.get("jdText") or confirmed_facts.get("jd_text") or ""
    resume_text_val = (confirmed_facts.get("resume") or {}).get("text") or ""

    if not job_title or not jd_text_val:
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "failed",
                "error_message": "Application is missing job title or job description — please complete the application first",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await _persist_generation_job_event(
            sb,
            TABLES,
            job_id=job_id,
            user_id=user_id,
            application_id=app_id,
            sequence_no=1,
            event_name="error",
            payload={
                "message": "Application is missing job title or job description — please complete the application first",
                "code": 400,
            },
        )
        return

    event_sequence = 0
    completed_steps = 0
    active_sources: set[str] = set()
    company_intel: Dict[str, Any] = {}

    async def check_cancel() -> bool:
        try:
            r = await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_jobs"])
                .select("cancel_requested")
                .eq("id", job_id)
                .maybe_single()
                .execute()
            )
            return bool((r.data or {}).get("cancel_requested"))
        except Exception as cancel_err:
            logger.warning("job_runner.cancel_check_failed", job_id=job_id, error=str(cancel_err)[:200])
            return False

    async def emit(event_name: str, payload: Dict[str, Any]) -> None:
        nonlocal event_sequence, completed_steps
        payload = {**payload}
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        stage = str(payload.get("stage") or payload.get("phase") or "")
        agent_name = str(payload.get("agent") or payload.get("pipeline_name") or _phase_to_agent_name(stage))
        status = str(payload.get("status") or "")
        source = payload.get("source")

        if event_name == "detail" and agent_name == "recon" and isinstance(source, str):
            if status == "running":
                active_sources.add(source)
            elif status in {"completed", "warning", "failed"}:
                active_sources.discard(source)

        if event_name == "progress":
            phase = str(payload.get("phase") or "")
            progress = int(payload.get("progress") or 0)
            step = int(payload.get("step") or 0)
            if phase.endswith("_done") or phase == "complete":
                completed_steps = max(completed_steps, step)

            await _persist_generation_job_update(
                sb,
                TABLES,
                job_id,
                {
                    "phase": phase,
                    "progress": progress,
                    "message": payload.get("message") or "",
                    "current_agent": agent_name,
                    "completed_steps": completed_steps,
                    "total_steps": int(payload.get("totalSteps") or _JOB_TOTAL_STEPS),
                    "active_sources_count": len(active_sources),
                },
            )
        elif event_name == "detail":
            await _persist_generation_job_update(
                sb,
                TABLES,
                job_id,
                {
                    "current_agent": agent_name,
                    "message": payload.get("message") or "",
                    "active_sources_count": len(active_sources),
                },
            )
        elif event_name == "agent_status":
            await _persist_generation_job_update(
                sb,
                TABLES,
                job_id,
                {
                    "current_agent": agent_name,
                    "message": payload.get("message") or f"{agent_name} {payload.get('status') or 'updated'}",
                },
            )

        event_sequence += 1
        await _persist_generation_job_event(
            sb,
            TABLES,
            job_id=job_id,
            user_id=user_id,
            application_id=app_id,
            sequence_no=event_sequence,
            event_name=event_name,
            payload=payload,
        )

    async def emit_progress(phase: str, step: int, progress: int, message: str) -> None:
        await emit(
            "progress",
            {
                "phase": phase,
                "step": step,
                "totalSteps": _JOB_TOTAL_STEPS,
                "progress": progress,
                "message": message,
            },
        )

    async def emit_detail(
        agent: str,
        message: str,
        status: str = "info",
        source: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "agent": agent,
            "message": message,
            "status": status,
        }
        if source:
            payload["source"] = source
        if url:
            payload["url"] = url
        if metadata:
            payload["metadata"] = metadata
        await emit("detail", payload)

    async def emit_error(message: str, code: int, retry_after_seconds: Optional[int] = None) -> None:
        payload: Dict[str, Any] = {"message": message, "code": code}
        if retry_after_seconds:
            payload["retryAfterSeconds"] = retry_after_seconds
        try:
            await _mark_application_generation_finished(
                sb,
                TABLES,
                app_id,
                application_row,
                requested_modules,
                status="cancelled" if code == 499 else "failed",
                error_message=message,
            )
        except Exception as app_err:
            logger.error("job_runner.application_state_error", job_id=job_id, error=str(app_err))
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "failed" if code != 499 else "cancelled",
                "error_message": message,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await emit("error", payload)

    async def emit_complete(result: Dict[str, Any]) -> None:
        await _persist_generation_result_to_application(
            sb,
            TABLES,
            application_row=application_row,
            requested_modules=requested_modules,
            result=result,
            user_id=user_id,
        )

        # P1-08: Run 4-dimension quality scoring (non-blocking)
        output_scores = {}
        try:
            from ai_engine.chains.output_scorer import OutputScorer
            scorer = OutputScorer(ai)
            profile_for_scoring = confirmed_facts

            cv_html = result.get("cv_html", "")
            cl_html = result.get("cover_letter_html", "")

            if cv_html and jd_text_val:
                output_scores["cv"] = await scorer.score("CV/Resume", cv_html, jd_text_val, profile_for_scoring)
            if cl_html and jd_text_val:
                output_scores["cover_letter"] = await scorer.score("Cover Letter", cl_html, jd_text_val, profile_for_scoring)
        except Exception as score_err:
            logger.warning("output_scoring_failed", job_id=job_id, error=str(score_err)[:200])

        if output_scores:
            result.setdefault("meta", {})["output_scores"] = output_scores

        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "succeeded",
                "progress": 100,
                "phase": "complete",
                "message": "Generation complete.",
                "current_agent": "nova",
                "completed_steps": _JOB_TOTAL_STEPS,
                "total_steps": _JOB_TOTAL_STEPS,
                "active_sources_count": 0,
                "result": result,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await emit("complete", {"progress": 100, "result": result})

    try:
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "running",
                "progress": 5,
                "phase": "initializing",
                "message": "Initializing AI engine…",
                "current_agent": "recon",
                "completed_steps": 0,
                "total_steps": _JOB_TOTAL_STEPS,
                "active_sources_count": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "error_message": None,
            },
        )
        await _set_application_modules_generating(
            sb,
            TABLES,
            app_id,
            application_row.get("modules"),
            requested_modules,
        )

        from ai_engine.client import AIClient
        from ai_engine.chains.company_intel import CompanyIntelChain
        from ai_engine.chains.role_profiler import RoleProfilerChain
        from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
        from ai_engine.chains.gap_analyzer import GapAnalyzerChain
        from ai_engine.chains.document_generator import DocumentGeneratorChain
        from ai_engine.chains.career_consultant import CareerConsultantChain
        from ai_engine.chains.validator import ValidatorChain

        ai = AIClient()
        company_str = company_name or "the company"

        await emit_progress("initializing", 0, 5, "Initializing AI engine…")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        await emit_progress("recon", 1, 8, "Recon is gathering company intelligence…")

        if company_name.strip():
            recon_chain = CompanyIntelChain(ai)

            async def on_recon_event(event: Dict[str, Any]) -> None:
                await emit_detail(
                    agent="recon",
                    message=str(event.get("message", "Recon update.")),
                    status=str(event.get("status", "info")),
                    source=event.get("source"),
                    url=event.get("url"),
                    metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else None,
                )

            company_intel = await recon_chain.gather_intel(
                company=company_name,
                job_title=job_title,
                jd_text=jd_text_val,
                on_event=on_recon_event,
            )
        else:
            await emit_detail(
                agent="recon",
                message="No company name provided, so Recon will use job-description-only signals.",
                status="warning",
                source="job_description",
            )
            company_intel = {
                "data_sources": ["Job description analysis"],
                "confidence": "low",
                "data_completeness": {
                    "website_data": False,
                    "jd_analysis": True,
                    "github_data": False,
                    "careers_page": False,
                },
            }

        await emit_progress("recon_done", 1, 14, "Recon finished gathering public intel ✓")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        profiler = RoleProfilerChain(ai)
        benchmark_chain = BenchmarkBuilderChain(ai)

        await emit_progress("profiling", 2, 18, "Atlas is parsing your resume and building the target benchmark…")
        await emit_detail("atlas", "Parsing resume text and role requirements.", "running", "resume")

        if resume_text_val.strip():
            user_profile, benchmark_data = await asyncio.gather(
                profiler.parse_resume(resume_text_val),
                benchmark_chain.create_ideal_profile(job_title, company_str, jd_text_val),
            )
        else:
            user_profile = {}
            benchmark_data = await benchmark_chain.create_ideal_profile(job_title, company_str, jd_text_val)

        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = _extract_keywords_from_jd(jd_text_val)

        await emit_detail(
            "atlas",
            f"Benchmark built with {len(keywords)} target keyword(s).",
            "completed",
            "benchmark",
            metadata={"keywords": keywords[:12]},
        )

        benchmark_cv_html = ""
        try:
            benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                user_profile=user_profile,
                benchmark_data=benchmark_data,
                job_title=job_title,
                company=company_str,
                jd_text=jd_text_val,
            )
        except Exception as bcv_err:
            logger.warning("job_stream.benchmark_cv_failed", error=str(bcv_err))

        await emit_progress("profiling_done", 2, 28, "Atlas finished the resume and benchmark analysis ✓")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        await emit_progress("gap_analysis", 3, 38, "Cipher is analyzing skill gaps and keyword misses…")
        await emit_detail("cipher", "Comparing your profile against the benchmark and job requirements.", "running", "gap_analysis")

        gap_chain = GapAnalyzerChain(ai)
        gap_analysis = await gap_chain.analyze_gaps(user_profile, benchmark_data, job_title, company_str)

        missing_keywords = gap_analysis.get("missing_keywords", []) or gap_analysis.get("missingKeywords", []) or []
        await emit_detail(
            "cipher",
            f"Gap analysis found {len(missing_keywords)} primary missing keyword(s).",
            "completed",
            "gap_analysis",
        )
        await emit_progress("gap_analysis_done", 3, 50, "Cipher finished the gap analysis ✓")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        # ── Phase 3b: Catalog-driven document planning ───────────────
        from app.services.document_catalog import discover_and_observe

        _doc_pack_plan_job = await discover_and_observe(
            db=sb, tables=TABLES, ai_client=ai,
            jd_text=jd_text_val, job_title=job_title,
            company=company_str, user_profile=user_profile,
            user_id=user_id, application_id=app_id,
            company_intel=company_intel,
        )

        await emit_progress("documents", 4, 58, "Quill is generating the CV, cover letter, and learning plan…")
        await emit_detail("quill", "Drafting the tailored CV, cover letter, and roadmap in parallel.", "running", "documents")

        consultant = CareerConsultantChain(ai)

        # ── v3: Use AgentPipeline with durable execution for documents ──
        _resume_stages = job.get("resume_from_stages") or {}
        _resume_from_legacy = job.get("resume_from_stage") or None
        _pipeline_context_base = {
            "user_id": user_id,
            "job_id": job_id,
            "application_id": app_id,
            "user_profile": user_profile,
            "job_title": job_title,
            "company": company_str,
            "jd_text": jd_text_val,
            "gap_analysis": gap_analysis,
            "resume_text": resume_text_val,
            "company_intel": company_intel,
        }

        def _ctx_for_pipeline(pipeline_name: str) -> dict:
            """Build per-pipeline context with scoped resume_from_stage."""
            ctx = dict(_pipeline_context_base)
            # v3.1: prefer per-pipeline resume markers; fall back to legacy blanket
            resume_stage = _resume_stages.get(pipeline_name) or _resume_from_legacy
            if resume_stage:
                ctx["resume_from_stage"] = resume_stage
            return ctx

        async def _agent_stage_cb(event: dict) -> None:
            await emit("agent_status", event)

        _use_agent_pipelines = _AGENT_PIPELINES_AVAILABLE

        if _use_agent_pipelines:
            from ai_engine.agents.pipelines import cv_generation_pipeline, cover_letter_pipeline

            cv_pipe = cv_generation_pipeline(ai_client=ai, on_stage_update=_agent_stage_cb, db=sb, tables=TABLES)

            cl_pipe = cover_letter_pipeline(ai_client=ai, on_stage_update=_agent_stage_cb, db=sb, tables=TABLES)

            cv_result_raw, cl_result_raw, roadmap = await asyncio.gather(
                cv_pipe.execute(_ctx_for_pipeline("cv_generation")),
                cl_pipe.execute(_ctx_for_pipeline("cover_letter")),
                consultant.generate_roadmap(gap_analysis, user_profile, job_title, company_str),
                return_exceptions=True,
            )

            cv_result: Any = None
            cv_html: Any = ""
            cl_html: Any = ""
            if isinstance(cv_result_raw, Exception):
                import traceback as _tb
                _cv_tb = "".join(_tb.format_exception(type(cv_result_raw), cv_result_raw, cv_result_raw.__traceback__))
                logger.error("job_runner.cv_pipeline_failed", error_msg=str(cv_result_raw), traceback=_cv_tb)
            else:
                cv_result = cv_result_raw
                cv_html = _extract_pipeline_html(cv_result.content)
            if isinstance(cl_result_raw, Exception):
                import traceback as _tb
                _cl_tb = "".join(_tb.format_exception(type(cl_result_raw), cl_result_raw, cl_result_raw.__traceback__))
                logger.error("job_runner.cl_pipeline_failed", error_msg=str(cl_result_raw), traceback=_cl_tb)
            else:
                cl_html = _extract_pipeline_html(cl_result_raw.content)
        else:
            cv_result: Any = None  # no PipelineResult in legacy path
            doc_chain = DocumentGeneratorChain(ai)
            cv_html, cl_html, roadmap = await asyncio.gather(
                doc_chain.generate_tailored_cv(
                    user_profile=user_profile,
                    job_title=job_title,
                    company=company_str,
                    jd_text=jd_text_val,
                    gap_analysis=gap_analysis,
                    resume_text=resume_text_val,
                ),
                doc_chain.generate_tailored_cover_letter(
                    user_profile=user_profile,
                    job_title=job_title,
                    company=company_str,
                    jd_text=jd_text_val,
                    gap_analysis=gap_analysis,
                ),
                consultant.generate_roadmap(gap_analysis, user_profile, job_title, company_str),
                return_exceptions=True,
            )

        if isinstance(cv_html, Exception):
            logger.error("job_stream.cv_failed", error=str(cv_html))
            cv_html = ""
        if isinstance(cl_html, Exception):
            logger.error("job_stream.cl_failed", error=str(cl_html))
            cl_html = ""
        if isinstance(roadmap, Exception):
            logger.error("job_stream.roadmap_failed", error=str(roadmap))
            roadmap = {}

        await emit_detail("quill", "Document architecture complete for the CV, cover letter, and learning plan.", "completed", "documents")
        await emit_progress("documents_done", 4, 72, "Quill finished the core application documents ✓")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        await emit_progress("portfolio", 5, 78, "Forge is building the personal statement and portfolio artifacts…")
        await emit_detail("forge", "Building the personal statement and portfolio outputs.", "running", "portfolio")

        ps_html = ""
        portfolio_html = ""
        if _use_agent_pipelines:
            from ai_engine.agents.pipelines import personal_statement_pipeline, portfolio_pipeline

            ps_pipe = personal_statement_pipeline(ai_client=ai, on_stage_update=_agent_stage_cb, db=sb, tables=TABLES)

            pf_pipe = portfolio_pipeline(ai_client=ai, on_stage_update=_agent_stage_cb, db=sb, tables=TABLES)

            try:
                ps_raw, pf_raw = await asyncio.gather(
                    ps_pipe.execute(_ctx_for_pipeline("personal_statement")),
                    pf_pipe.execute(_ctx_for_pipeline("portfolio")),
                    return_exceptions=True,
                )
                if not isinstance(ps_raw, Exception):
                    ps_html = _extract_pipeline_html(ps_raw.content)
                if not isinstance(pf_raw, Exception):
                    portfolio_html = _extract_pipeline_html(pf_raw.content)
            except Exception as phase5_err:
                logger.error("job_runner.phase5_pipeline_error", error=str(phase5_err))
        else:
            doc_chain_ps = DocumentGeneratorChain(ai)
            try:
                ps_result, portfolio_result = await asyncio.gather(
                    doc_chain_ps.generate_tailored_personal_statement(
                        user_profile=user_profile,
                        job_title=job_title,
                        company=company_str,
                        jd_text=jd_text_val,
                        gap_analysis=gap_analysis,
                        resume_text=resume_text_val,
                    ),
                    doc_chain_ps.generate_tailored_portfolio(
                        user_profile=user_profile,
                        job_title=job_title,
                        company=company_str,
                        jd_text=jd_text_val,
                        gap_analysis=gap_analysis,
                        resume_text=resume_text_val,
                    ),
                    return_exceptions=True,
                )
                if not isinstance(ps_result, Exception):
                    ps_html = ps_result if isinstance(ps_result, str) else ""
                if not isinstance(portfolio_result, Exception):
                    portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
            except Exception as phase4_err:
                logger.error("job_stream.phase4_error", error=str(phase4_err))

        await emit_detail("forge", "Portfolio-related artifacts are ready.", "completed", "portfolio")
        await emit_progress("portfolio_done", 5, 86, "Forge finished the portfolio artifacts ✓")
        if await check_cancel():
            await emit_error("Generation cancelled.", 499)
            return

        await emit_progress("validation", 6, 92, "Sentinel is validating document quality and ATS readiness…")
        await emit_detail("sentinel", "Running final document quality checks.", "running", "validation")

        validation: Dict[str, Any] = {}
        try:
            validator = ValidatorChain(ai)
            cv_valid, cv_validation = await validator.validate_document(
                document_type="Tailored CV",
                content=cv_html[:3000] if isinstance(cv_html, str) and cv_html else "",
                profile_data=user_profile,
            )
            validation["cv"] = {
                "valid": cv_valid,
                "qualityScore": cv_validation.get("quality_score", 0),
                "issues": len(cv_validation.get("issues", [])),
            }
        except Exception as val_err:
            logger.warning("job_stream.validation_skipped", error=str(val_err))

        await emit_detail("sentinel", "Validation and ATS checks completed.", "completed", "validation")
        await emit_progress("validation_done", 6, 96, "Sentinel finished the quality checks ✓")
        await emit_progress("formatting", 7, 98, "Nova is packaging your final application bundle…")
        await emit_detail("nova", "Packaging the final application bundle and scorecard.", "running", "formatting")

        response = _format_response(
            benchmark_data=benchmark_data,
            gap_analysis=gap_analysis,
            roadmap=roadmap if isinstance(roadmap, dict) else {},
            cv_html=cv_html if isinstance(cv_html, str) else "",
            cl_html=cl_html if isinstance(cl_html, str) else "",
            ps_html=ps_html,
            portfolio_html=portfolio_html,
            validation=validation,
            keywords=keywords,
            job_title=job_title,
            benchmark_cv_html=benchmark_cv_html,
        )
        response["meta"] = {
            **(response.get("meta") or {}),
            "company_intel": company_intel,
            "final_analysis": cv_result.final_analysis_report if cv_result else None,
            "validation_report": cv_result.validation_report if cv_result else None,
            "citations": cv_result.citations if cv_result else None,
            "evidence_summary": _build_evidence_summary(cv_result) if cv_result else None,
            "workflow_state": cv_result.workflow_state if cv_result else None,
        }

        await emit_detail("nova", "Final application bundle ready.", "completed", "formatting")
        await emit_complete(response)
        logger.info("job_runner.complete", job_id=job_id, overall_score=response["scores"]["overall"])
    except Exception as e:
        classified = _classify_ai_error(e)
        if classified:
            code = int(classified["code"])
            msg = str(classified["message"])
            retry_after = classified.get("retry_after_seconds")
            logger.error("job_runner.ai_error", job_id=job_id, code=code, message=msg)
            await emit_error(msg, code, retry_after)
        else:
            logger.error("job_runner.error", job_id=job_id, error=str(e), traceback=traceback.format_exc())
            await emit_error("AI generation failed due to an unexpected error. Please try again.", 500)


async def _run_generation_job_via_runtime(job_id: str, user_id: str) -> None:
    """Run a generation job using PipelineRuntime with DatabaseSink."""
    try:
        await asyncio.wait_for(
            _run_generation_job_inner_runtime(job_id, user_id),
            timeout=1800,
        )
    except asyncio.TimeoutError:
        logger.error("job_runtime.timeout", job_id=job_id)
        await _finalize_orphaned_job(
            job_id, status="failed",
            error_message="Generation timed out after 30 minutes.",
        )
    except asyncio.CancelledError:
        logger.warning("job_runtime.cancelled", job_id=job_id)
        await _finalize_orphaned_job(job_id, status="cancelled", error_message="Cancelled.")
    except Exception as e:
        logger.error("job_runtime.unexpected", job_id=job_id, error=str(e))
        await _finalize_orphaned_job(job_id, status="failed", error_message="Unexpected failure.")
    finally:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)


async def _run_generation_job_inner_runtime(job_id: str, user_id: str) -> None:
    """Execute a generation job through PipelineRuntime with DB-backed event persistence."""
    fetched = await _fetch_job_and_application(job_id, user_id)
    if not fetched:
        return
    sb, job, app_data, application_id, requested_modules = fetched

    from app.core.database import TABLES

    # Build runtime with DatabaseSink
    sink = _DatabaseSink(
        db=sb, tables=TABLES, job_id=job_id,
        user_id=user_id, application_id=application_id,
        requested_modules=requested_modules,
    )
    config = _RuntimeConfig(
        mode=_ExecutionMode.JOB,
        timeout=1800,
        user_id=user_id,
        job_id=job_id,
        application_id=application_id,
        requested_modules=requested_modules,
    )
    runtime = _PipelineRuntime(config=config, event_sink=sink)

    # Mark job as running
    await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .update({"status": "running", "progress": 1})
        .eq("id", job_id).execute()
    )

    confirmed_facts = app_data.get("confirmed_facts") or {}
    try:
        result = await runtime.execute({
            "job_title": confirmed_facts.get("jobTitle") or confirmed_facts.get("job_title") or "",
            "company": confirmed_facts.get("company") or "",
            "jd_text": confirmed_facts.get("jdText") or confirmed_facts.get("jd_text") or "",
            "resume_text": (confirmed_facts.get("resume") or {}).get("text") or "",
        })

        # Use the canonical persistence helper — handles all dynamic doc fields
        await _persist_generation_result_to_application(
            sb, TABLES,
            application_row=app_data,
            requested_modules=requested_modules,
            result=result,
            user_id=user_id,
        )

        # Persist doc_pack_plan to applications if present
        doc_pack_plan = result.get("docPackPlan")
        if doc_pack_plan:
            try:
                await asyncio.to_thread(
                    lambda: sb.table(TABLES["applications"])
                    .update({"doc_pack_plan": doc_pack_plan})
                    .eq("id", application_id)
                    .execute()
                )
            except Exception as dpp_err:
                logger.warning("job_runtime.doc_pack_plan_persist_failed", error=str(dpp_err)[:200])

        # Mark job complete
        await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .update({"status": "succeeded", "progress": 100})
            .eq("id", job_id).execute()
        )
        logger.info("job_runtime.complete", job_id=job_id)

    except Exception as e:
        _err_msg = str(e)
        logger.error("job_runtime.failed", job_id=job_id, error=_err_msg[:300])
        await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .update({"status": "failed", "progress": 0, "message": _err_msg[:500]})
            .eq("id", job_id).execute()
        )
        # Reset application modules from "generating" → "error" so UI isn't stuck
        try:
            await _mark_application_generation_finished(
                sb, TABLES,
                application_id=application_id,
                application_row=None,
                requested_modules=requested_modules,
                status="failed",
                error_message=f"{_err_msg[:200]}. Click Regenerate to retry.",
            )
        except Exception as mark_err:
            logger.warning("job_runtime.mark_failed_error", error=str(mark_err)[:200])
        raise


def _start_generation_job(job_id: str, user_id: str) -> None:
    if job_id in _ACTIVE_GENERATION_TASKS:
        return

    # Prefer PipelineRuntime-backed execution when available
    if _RUNTIME_AVAILABLE:
        task = asyncio.create_task(_run_generation_job_via_runtime(job_id, user_id))
    else:
        task = asyncio.create_task(_run_generation_job(job_id, user_id))
    _ACTIVE_GENERATION_TASKS[job_id] = task

    def _cleanup(completed_task: asyncio.Task) -> None:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)
        try:
            completed_task.result()
        except asyncio.CancelledError:
            # External cancellation — _run_generation_job already handles finalization
            logger.warning("generation_task_externally_cancelled", job_id=job_id)
        except Exception as e:
            logger.error("generation_task_failed", job_id=job_id, error=str(e))

    task.add_done_callback(_cleanup)




@router.post("/jobs")
@limiter.limit("3/minute")
async def create_generation_job(
    request: Request,
    req: GenerationJobRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a DB-backed generation job. Returns {job_id} immediately."""
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    await _ensure_generation_job_schema_ready(sb, TABLES)

    # Verify the application belongs to this user
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id,confirmed_facts,modules")
        .eq("id", req.application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    requested_modules = _normalize_requested_modules(req.requested_modules)

    # Create job row FIRST — if this fails, no module state change happens.
    job_row = {
        "user_id": user_id,
        "application_id": req.application_id,
        "requested_modules": requested_modules,
        "status": "queued",
        "progress": 0,
    }
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .insert(job_row)
        .execute()
    )
    job_id = job_resp.data[0]["id"]

    # Emit initial "queued" event so frontend can subscribe immediately
    try:
        await _persist_generation_job_event(
            sb, TABLES,
            job_id=job_id,
            user_id=user_id,
            application_id=req.application_id,
            sequence_no=0,
            event_name="queued",
            payload={"status": "queued", "progress": 0, "message": "Job queued for processing."},
        )
    except Exception as q_err:
        logger.warning("create_job.queued_event_failed", job_id=job_id, error=str(q_err)[:200])

    # Now that the job exists, mark modules as generating.
    # If this fails, the job is queued but modules stay idle — the job
    # runner will set them on startup anyway.
    try:
        await _set_application_modules_generating(
            sb,
            TABLES,
            req.application_id,
            app_resp.data.get("modules"),
            requested_modules,
        )
    except Exception as mod_err:
        logger.warning("create_job.module_state_failed", job_id=job_id, error=str(mod_err))

    _start_generation_job(job_id, user_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}/stream")
@limiter.limit("30/minute")
async def stream_generation_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Tail a generation job's persisted SSE events and current status."""
    validate_uuid(job_id, "job_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Fetch job
    # NOTE: Using .limit(1) instead of .maybe_single() because the
    # 'message' column name in generation_jobs conflicts with
    # postgrest-py's error response parsing, causing a spurious 204.
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    job = job_resp.data[0]

    if job.get("status") in {"queued", "running"} and job_id not in _ACTIVE_GENERATION_TASKS:
        _start_generation_job(job_id, user_id)

    async def event_stream() -> AsyncGenerator[str, None]:
        last_sequence = 0
        idle_polls = 0

        while True:
            events_resp = await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_job_events"])
                .select("*")
                .eq("job_id", job_id)
                .gt("sequence_no", last_sequence)
                .order("sequence_no")
                .limit(200)
                .execute()
            )
            rows = events_resp.data or []
            if rows:
                idle_polls = 0
                for row in rows:
                    last_sequence = max(last_sequence, int(row.get("sequence_no") or 0))
                    payload = row.get("payload") or {}
                    yield _sse(str(row.get("event_name") or "progress"), payload)
            else:
                idle_polls += 1

            latest_job_resp = await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_jobs"])
                .select("status")
                .eq("id", job_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            latest_job = latest_job_resp.data or {}
            status = latest_job.get("status")
            if status in {"succeeded", "failed", "cancelled"}:
                final_events = await asyncio.to_thread(
                    lambda: sb.table(TABLES["generation_job_events"])
                    .select("*")
                    .eq("job_id", job_id)
                    .gt("sequence_no", last_sequence)
                    .order("sequence_no")
                    .limit(200)
                    .execute()
                )
                for row in final_events.data or []:
                    last_sequence = max(last_sequence, int(row.get("sequence_no") or 0))
                    payload = row.get("payload") or {}
                    yield _sse(str(row.get("event_name") or "progress"), payload)
                break

            if idle_polls >= 2:
                yield ": keepalive\n\n"
                idle_polls = 0

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/jobs/{job_id}/cancel")
@limiter.limit("10/minute")
async def cancel_generation_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Request cancellation of a running generation job."""
    validate_uuid(job_id, "job_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .update({"cancel_requested": True})
        .eq("id", job_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"cancelled": True}


@router.get("/jobs/{job_id}/replay")
@limiter.limit("10/minute")
async def replay_generation_job(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Replay a generation job for diagnostic analysis.

    Reconstructs the job timeline from persisted events, loads evidence
    and citations, classifies the failure, and returns a structured
    replay report.
    """
    validate_uuid(job_id, "job_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Verify job exists and belongs to user
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("id,user_id,status,application_id,requested_modules")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    job = job_resp.data

    # Load evidence ledger items
    evidence_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["evidence_ledger_items"])
        .select("*")
        .eq("job_id", job_id)
        .execute()
    )
    evidence_items = evidence_resp.data or []

    # Load claim citations
    citation_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["claim_citations"])
        .select("*")
        .eq("job_id", job_id)
        .execute()
    )
    citations = citation_resp.data or []

    # Run the replay engine
    try:
        from ai_engine.evals.replay_runner import ReplayRunner
        from ai_engine.agents.workflow_runtime import WorkflowEventStore

        event_store = WorkflowEventStore(sb, TABLES)
        runner = ReplayRunner(event_store)
        report = await runner.replay_job(
            job_id,
            evidence_items=evidence_items,
            citations=citations,
            job_status=job.get("status", "unknown"),
        )
        return {"replay_report": report.to_dict()}
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Replay engine not available",
        )
    except Exception as e:
        logger.error("replay_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Replay analysis failed",
        )


# ── Job status polling (P2-04) ────────────────────────────────────────

@router.get("/jobs/{job_id}/status")
@limiter.limit("60/minute")
async def get_generation_job_status(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Lightweight status poll for clients that lost the SSE connection.

    Returns the current job status, progress, and latest event summary
    without opening a long-lived stream.
    """
    validate_uuid(job_id, "job_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("id,status,progress,error_message,requested_modules,created_at,finished_at")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    job = job_resp.data[0]

    # Fetch the most recent event to give the client a progress summary
    latest_event_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_job_events"])
        .select("event_name,payload,created_at,sequence_no")
        .eq("job_id", job_id)
        .order("sequence_no", desc=True)
        .limit(1)
        .execute()
    )
    latest_event = (latest_event_resp.data or [None])[0]

    return {
        "job_id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "error_message": job.get("error_message"),
        "requested_modules": job.get("requested_modules", []),
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
        "latest_event": {
            "event_name": latest_event.get("event_name"),
            "payload": latest_event.get("payload"),
            "sequence_no": latest_event.get("sequence_no"),
        } if latest_event else None,
        "is_active": job_id in _ACTIVE_GENERATION_TASKS,
    }


@router.post("/jobs/{job_id}/retry")
@limiter.limit("3/minute")
async def retry_generation_modules(
    request: Request,
    job_id: str,
    req: RetryModulesRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Retry specific failed modules from an existing generation job.

    Creates a new child job that only generates the requested modules,
    reusing the original application context. The original job must be
    in a terminal state (succeeded, failed, or cancelled).
    """
    validate_uuid(job_id, "job_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Verify original job exists and is terminal
    orig_job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("id,status,application_id,requested_modules,user_id")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not orig_job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    orig_job = orig_job_resp.data[0]
    if orig_job.get("status") not in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail="Can only retry modules from a completed, failed, or cancelled job",
        )

    application_id = orig_job["application_id"]

    # Verify application belongs to user
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id,modules")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    retry_modules = _normalize_requested_modules(req.modules)

    # Create a new child job for only the retry modules
    job_row = {
        "user_id": user_id,
        "application_id": application_id,
        "requested_modules": retry_modules,
        "status": "queued",
        "progress": 0,
        "parent_job_id": job_id,
    }
    new_job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .insert(job_row)
        .execute()
    )
    new_job_id = new_job_resp.data[0]["id"]

    # Emit initial event
    try:
        await _persist_generation_job_event(
            sb, TABLES,
            job_id=new_job_id,
            user_id=user_id,
            application_id=application_id,
            sequence_no=0,
            event_name="queued",
            payload={
                "status": "queued",
                "progress": 0,
                "message": f"Retrying modules: {', '.join(retry_modules)}",
                "parent_job_id": job_id,
            },
        )
    except Exception as q_err:
        logger.warning("retry_job.queued_event_failed", job_id=new_job_id, error=str(q_err)[:200])

    # Mark retry modules as generating
    try:
        await _set_application_modules_generating(
            sb, TABLES, application_id,
            app_resp.data.get("modules"),
            retry_modules,
        )
    except Exception as mod_err:
        logger.warning("retry_job.module_state_failed", job_id=new_job_id, error=str(mod_err))

    _start_generation_job(new_job_id, user_id)
    return {"job_id": new_job_id, "retrying_modules": retry_modules, "parent_job_id": job_id}



STALE_JOB_TIMEOUT_MINUTES = 45


async def cleanup_stale_generation_jobs() -> int:
    """Sweep for generation jobs stuck in running/queued state beyond the timeout.

    Safe to call periodically from a scheduler or health check.
    Returns the number of jobs cleaned up.
    """
    try:
        from app.core.database import get_supabase, TABLES

        sb = get_supabase()
        _cutoff = datetime.now(timezone.utc).isoformat()

        # Fetch jobs that are still running/queued
        resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .select("id,status,user_id,application_id,requested_modules,created_at")
            .in_("status", ["running", "queued"])
            .execute()
        )
        stuck_jobs = resp.data or []
        if not stuck_jobs:
            return 0

        cleaned = 0
        now = datetime.now(timezone.utc)
        for job in stuck_jobs:
            job_id = job["id"]

            # Skip jobs that are actively being processed
            if job_id in _ACTIVE_GENERATION_TASKS:
                task = _ACTIVE_GENERATION_TASKS[job_id]
                if not task.done():
                    continue

            # Check if job is older than the timeout
            created_at_str = job.get("created_at", "")
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                age_minutes = (now - created_at).total_seconds() / 60
            except (ValueError, TypeError):
                age_minutes = STALE_JOB_TIMEOUT_MINUTES + 1  # assume stale if can't parse

            if age_minutes < STALE_JOB_TIMEOUT_MINUTES:
                continue

            logger.warning(
                "stale_job_cleanup",
                job_id=job_id,
                age_minutes=round(age_minutes, 1),
                status=job.get("status"),
            )
            await _finalize_orphaned_job(
                job_id,
                status="failed",
                error_message=f"Generation timed out after {round(age_minutes)} minutes. Please try again.",
            )
            cleaned += 1

        return cleaned
    except Exception as e:
        logger.error("stale_job_cleanup_failed", error=str(e))
        return 0


async def recover_inflight_generation_jobs() -> int:
    """
    Called on startup: attempt intelligent recovery of inflight jobs.

    For each running/queued job:
    - Load the event log and reconstruct workflow state.
    - If the job made material progress and is safely resumable,
      mark it for retry (status='queued', resume_from_stage set) instead
      of blanket-failing.
    - If not safely resumable, mark as failed with diagnostic info.

    Conservative policy: only mark as resumable if we have a clean boundary
    (completed stages, no RUNNING stages). Never attempt automatic restart
    from this recovery function — that would happen when the job stream
    reconnects or when the user clicks Regenerate.
    """
    try:
        from app.core.database import get_supabase, TABLES

        sb = get_supabase()
        resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .select("id,user_id,status,application_id,requested_modules")
            .in_("status", ["running", "queued"])
            .execute()
        )
        inflight_jobs = resp.data or []
        if not inflight_jobs:
            _ACTIVE_GENERATION_TASKS.clear()
            return 0

        recovered_count = 0
        for job in inflight_jobs:
            job_id = job["id"]
            _user_id = job.get("user_id", "")

            # Try event-based recovery if agent pipelines + event store available
            if _AGENT_PIPELINES_AVAILABLE:
                try:
                    store = _WorkflowEventStore(sb, TABLES)
                    events = await store.load_events(job_id)

                    if events:
                        # v3.1: per-pipeline recovery — reconstruct each pipeline's
                        # state and determine per-pipeline resume points
                        resume_stages: dict[str, str | None] = {}
                        any_resumable = False
                        total_completed = 0

                        for pname in _PIPELINE_NAMES:
                            pipeline_events = await store.load_events_for_pipeline(job_id, pname)
                            if not pipeline_events:
                                resume_stages[pname] = None
                                continue
                            pstate = _reconstruct_state(pipeline_events, job_id)
                            completed = _get_completed_stages(pstate)
                            total_completed += len(completed)
                            if _is_safely_resumable(pstate):
                                from ai_engine.agents.workflow_runtime import get_resume_point
                                resume_stages[pname] = get_resume_point(pstate, _STAGE_ORDER)
                                any_resumable = True
                            elif pstate.status == "succeeded":
                                resume_stages[pname] = None  # already done
                            else:
                                resume_stages[pname] = None

                        if any_resumable:
                            # Filter out completed/None pipelines
                            active_resume = {k: v for k, v in resume_stages.items() if v is not None}
                            await asyncio.to_thread(
                                lambda jid=job_id, rs=active_resume, rc=total_completed: sb.table(TABLES["generation_jobs"])
                                .update({
                                    "status": "queued",
                                    "resume_from_stages": rs,
                                    "recovery_attempts": rc,
                                    "error_message": f"Server restarted — auto-queued ({total_completed} stages completed across pipelines)",
                                })
                                .eq("id", jid)
                                .execute()
                            )
                            logger.info(
                                "job_recovery.resumable",
                                job_id=job_id,
                                resume_stages=active_resume,
                                total_completed=total_completed,
                            )
                            recovered_count += 1
                            continue
                except Exception as recovery_err:
                    logger.warning("job_recovery.state_check_failed", job_id=job_id, error=str(recovery_err))

            # Fallback: mark as failed (same as v2 behavior) + reconcile module states
            fail_msg = "Server restarted — please click Regenerate to try again"
            await asyncio.to_thread(
                lambda jid=job_id: sb.table(TABLES["generation_jobs"])
                .update({
                    "status": "failed",
                    "error_message": fail_msg,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", jid)
                .execute()
            )
            # Reconcile application module states so they don't stay "generating"
            recovery_app_id = job.get("application_id", "")
            recovery_modules = _normalize_requested_modules(job.get("requested_modules"))
            if recovery_app_id and recovery_modules:
                try:
                    await _mark_application_generation_finished(
                        sb, TABLES, recovery_app_id, None, recovery_modules,
                        status="failed", error_message=fail_msg,
                    )
                except Exception as mod_err:
                    logger.warning("job_recovery.module_reconcile_failed", job_id=job_id, error=str(mod_err))
            recovered_count += 1

        _ACTIVE_GENERATION_TASKS.clear()
        return recovered_count
    except Exception as e:
        logger.warning("recover_inflight_jobs_failed", error=str(e))
        return 0


async def cleanup_orphaned_generating_modules() -> int:
    """Sweep for application modules stuck in 'generating'/'queued' with no active job.

    This catches cases where:
    - The frontend set modules to 'generating' but the job POST failed
    - A server restart cleaned up the job but missed the module states
    - Any other edge case leaving modules orphaned

    Safe to call on startup and periodically.
    """
    try:
        from app.core.database import get_supabase, TABLES
        import time

        sb = get_supabase()

        # Find all active (running/queued) generation jobs
        jobs_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .select("application_id")
            .in_("status", ["running", "queued"])
            .execute()
        )
        active_app_ids = {j["application_id"] for j in (jobs_resp.data or []) if j.get("application_id")}

        # Find applications with modules in 'generating' or 'queued' state
        # Supabase doesn't support JSON field queries well, so fetch recent apps
        apps_resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["applications"])
            .select("id,modules")
            .order("updated_at", desc=True)
            .limit(100)
            .execute()
        )

        cleaned = 0
        timestamp = int(time.time() * 1000)
        for app in (apps_resp.data or []):
            app_id = app["id"]
            modules = app.get("modules") or {}

            # Skip apps with active jobs — those are legitimately generating
            if app_id in active_app_ids:
                continue

            has_stuck = False
            for key, val in modules.items():
                if isinstance(val, dict) and val.get("state") in ("generating", "queued"):
                    has_stuck = True
                    modules[key] = {
                        "state": "error",
                        "updatedAt": timestamp,
                        "error": "Generation interrupted. Click Regenerate to retry.",
                    }

            if has_stuck:
                await asyncio.to_thread(
                    lambda aid=app_id, mods=modules: sb.table(TABLES["applications"])
                    .update({"modules": mods})
                    .eq("id", aid)
                    .execute()
                )
                cleaned += 1
                logger.info("orphan_module_cleanup", application_id=app_id)

        return cleaned
    except Exception as e:
        logger.warning("orphan_module_cleanup_failed", error=str(e))
        return 0
