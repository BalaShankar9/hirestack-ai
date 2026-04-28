"""DB-backed generation jobs: endpoints, infrastructure, runtime, and cleanup."""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, validate_uuid
from app.core.security import limiter

from .schemas import GenerationJobRequest, RetryModulesRequest
from .helpers import (
    _AGENT_PIPELINES_AVAILABLE,
    _sse,
    _PIPELINE_NAMES,
    _STAGE_ORDER,
    finalize_job_status_payload,
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
    from .helpers import (  # noqa: F401
        cv_generation_pipeline, cover_letter_pipeline,
        personal_statement_pipeline, portfolio_pipeline,
        PipelineResult,
    )
except ImportError:
    pass

router = APIRouter()

_ACTIVE_GENERATION_TASKS: Dict[str, asyncio.Task] = {}
_JOB_TOTAL_STEPS = 7


def _get_model_health_summary() -> Dict[str, Any]:
    """Best-effort model health for job status responses."""
    try:
        from ai_engine.model_router import get_model_health
        return get_model_health()
    except Exception:
        return {}


_DEFAULT_REQUESTED_MODULES = [
    "benchmark",
    "gaps",
    "learningPlan",
    "cv",
    "resume",
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
_IDENTITY_KEYS = {"benchmark", "cv", "resume", "portfolio", "scorecard", "gaps"}


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _apply_preferred_lock(
    variants: List[Dict[str, Any]],
    scores: Optional[Dict[str, Any]],
    document: str,
) -> str:
    """Phase D.5: re-lock the variant whose style has the highest
    learned outcome score, then return its content for canonical use.

    Returns the (possibly unchanged) canonical content.  No-op when
    scores are missing, when the preferred variant is already locked,
    or when the preferred variant isn't present in the list.
    """
    if not variants:
        return ""
    try:
        from ai_engine.agents.style_outcome_scorer import preferred_style
    except Exception:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    target = preferred_style(scores, document, fallback="")
    if not target:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    has_target = any(
        isinstance(v, dict) and v.get("variant") == target and (v.get("content") or "").strip()
        for v in variants
    )
    if not has_target:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    new_canonical = ""
    for v in variants:
        if not isinstance(v, dict):
            continue
        is_target = v.get("variant") == target
        v["locked"] = bool(is_target)
        if is_target:
            new_canonical = v.get("content", "") or ""
    return new_canonical


def _default_module_states() -> Dict[str, Dict[str, Any]]:
    return {
        "benchmark": {"state": "idle"},
        "gaps": {"state": "idle"},
        "learningPlan": {"state": "idle"},
        "cv": {"state": "idle"},
        "resume": {"state": "idle"},
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
    if module_key == "resume":
        return bool(str(application_row.get("resume_html") or "").strip())
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

    # PGRST204 = "Could not find the '<col>' column of '<table>' in the
    # schema cache" — happens when a migration hasn't been applied to
    # production yet.  We do NOT want one missing column to throw away
    # an entire generation run; the user has waited for this.  Strip the
    # offending column and retry, logging loudly so the gap is visible.
    #
    # Cap retries so a malformed patch (every column missing) can't loop
    # forever.  In practice production has at most one or two columns
    # behind at any time.
    max_retries = 8
    working_patch = dict(patch)
    dropped: list[str] = []

    for _ in range(max_retries):
        try:
            await asyncio.to_thread(
                lambda: sb.table(tables["applications"])
                .update(working_patch)
                .eq("id", application_id)
                .execute()
            )
            if dropped:
                logger.error(
                    "application_patch_persisted_with_dropped_columns",
                    application_id=application_id,
                    dropped_columns=dropped,
                    note="apply pending migrations to recover full persistence",
                )
            return
        except Exception as exc:
            err_text = str(exc)
            # PostgREST schema-cache miss — extract the column name from
            # the error message and drop it from the patch.
            if "PGRST204" in err_text or "schema cache" in err_text.lower():
                missing_col: Optional[str] = None
                # Message shape: "Could not find the 'resume_html' column of 'applications' in the schema cache"
                import re
                m = re.search(r"the '([^']+)' column", err_text)
                if m:
                    missing_col = m.group(1)
                if missing_col and missing_col in working_patch:
                    working_patch.pop(missing_col, None)
                    dropped.append(missing_col)
                    logger.warning(
                        "application_patch_dropping_missing_column",
                        application_id=application_id,
                        column=missing_col,
                        remaining_keys=sorted(working_patch.keys()),
                    )
                    if not working_patch:
                        logger.error(
                            "application_patch_empty_after_drops",
                            application_id=application_id,
                            dropped_columns=dropped,
                        )
                        return
                    continue
            # Any other error, or PGRST204 we couldn't parse — re-raise.
            raise

    logger.error(
        "application_patch_max_retries_exhausted",
        application_id=application_id,
        dropped_columns=dropped,
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
            .select(
                # All columns the job runner will write back.  If any are
                # missing, fail fast with a clear "apply migrations"
                # message instead of running a 60s pipeline and then
                # losing data on persistence.
                "id,resume_html,personal_statement_html,portfolio_html,"
                "discovered_documents,generated_documents,benchmark_documents,"
                "document_strategy,company_intel,validation,scorecard,scores"
            )
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
                .select("id,modules,cv_html,resume_html,cover_letter_html,personal_statement_html,portfolio_html,benchmark,gaps,learning_plan,scores,scorecard")
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

    # Phase D.2: persist multi-variant CV bundle into the dedicated
    # cv_variants JSONB column.  (Originally wrote to cv_versions but
    # that collided with the frontend's snapshot-history payload —
    # see migration 20260421120000.)  One variant is `locked: True` by
    # convention (the canonical CV that's also in cv_html).  The lock
    # endpoint can flip locks and update cv_html accordingly.
    _cv_variants_out = result.get("cvVariants")
    if isinstance(_cv_variants_out, list) and _cv_variants_out:
        patch["cv_variants"] = _cv_variants_out

    if "coverLetter" in requested and result.get("coverLetterHtml"):
        patch["cover_letter_html"] = result["coverLetterHtml"]

    if "personalStatement" in requested and result.get("personalStatementHtml"):
        patch["personal_statement_html"] = result["personalStatementHtml"]

    # Phase D.3: persist multi-variant personal statement bundle into
    # the dedicated ps_variants column (parallels D.2 split, see migration
    # 20260421120000).
    _ps_variants_out = result.get("personalStatementVariants")
    if isinstance(_ps_variants_out, list) and _ps_variants_out:
        patch["ps_variants"] = _ps_variants_out

    if "portfolio" in requested and result.get("portfolioHtml"):
        patch["portfolio_html"] = result["portfolioHtml"]

    # Resume is generated alongside CV — persist if content exists
    if result.get("resumeHtml"):
        patch["resume_html"] = result["resumeHtml"]

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

    # ── Content-aware module state: only mark "ready" if actual content exists ──
    for module_key in requested_modules:
        has_content = False
        if module_key == "benchmark":
            has_content = bool(patch.get("benchmark"))
        elif module_key == "gaps":
            has_content = bool(patch.get("gaps"))
        elif module_key == "learningPlan":
            lp = result.get("learningPlan", {})
            has_content = bool(lp.get("focus") or lp.get("plan") or lp.get("resources"))
        elif module_key == "cv":
            has_content = bool((patch.get("cv_html") or "").strip())
        elif module_key == "resume":
            has_content = bool((patch.get("resume_html") or "").strip())
        elif module_key == "coverLetter":
            has_content = bool((patch.get("cover_letter_html") or "").strip())
        elif module_key == "personalStatement":
            has_content = bool((patch.get("personal_statement_html") or "").strip())
        elif module_key == "portfolio":
            has_content = bool((patch.get("portfolio_html") or "").strip())
        elif module_key == "scorecard":
            has_content = bool(patch.get("scorecard") or patch.get("scores"))
        else:
            has_content = True  # Unknown modules default to ready

        if has_content:
            modules[module_key] = {"state": "ready", "updatedAt": timestamp}
        else:
            modules[module_key] = {
                "state": "error",
                "updatedAt": timestamp,
                "error": f"{module_key} produced no content. Try regenerating this module.",
            }
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

    # ── Populate the document_library table ──────────────────────────
    try:
        await _sync_document_library(
            sb, tables,
            user_id=user_id,
            application_id=application_id,
            result=result,
            requested=requested,
        )
    except Exception as dl_err:
        logger.warning("job_runner.document_library_sync_failed", application_id=application_id, error=str(dl_err))

    # ── Post-generation platform hooks (non-blocking) ────────────────
    try:
        await _run_post_generation_hooks(
            sb, tables,
            user_id=user_id,
            application_id=application_id,
            result=result,
            requested=requested,
            application_row=application_row,
        )
    except Exception as hook_err:
        logger.warning("job_runner.post_generation_hooks_failed", application_id=application_id, error=str(hook_err))


async def _run_post_generation_hooks(
    sb: Any,
    tables: Dict[str, str],
    *,
    user_id: str,
    application_id: str,
    result: Dict[str, Any],
    requested: set,
    application_row: Dict[str, Any],
) -> None:
    """Run platform-level sync after generation completes.

    These hooks connect the workspace-level generation to the broader platform
    intelligence layer (global skills, knowledge recommendations, career snapshots).
    All hooks are best-effort — failures are logged but never block the generation result.
    """

    # 1. Auto-sync global skill gaps from the new gap analysis
    if "gaps" in requested and result.get("gaps"):
        try:
            from app.services.global_skills import GlobalSkillsService
            skills_svc = GlobalSkillsService()
            await skills_svc.sync_gaps_from_applications(user_id)
            logger.info("post_gen.skills_gaps_synced", user_id=user_id, application_id=application_id)
        except Exception as e:
            logger.warning("post_gen.skills_gaps_sync_failed", error=str(e)[:200])

    # 2. Auto-extract skills from resume/profile into user_skills table
    confirmed_facts = application_row.get("confirmed_facts") or {}
    resume_text = confirmed_facts.get("resume", {}).get("text", "") if isinstance(confirmed_facts.get("resume"), dict) else ""
    benchmark_data = result.get("benchmark") or {}
    # Extract skills from benchmark keywords + gap strengths
    skills_to_upsert = []
    for kw in (benchmark_data.get("keywords") or [])[:20]:
        if isinstance(kw, str) and kw.strip():
            skills_to_upsert.append({"skill_name": kw.strip(), "source": "gap_analysis", "category": "technical"})
    for strength in (result.get("gaps") or {}).get("strengths", [])[:15]:
        if isinstance(strength, str) and strength.strip():
            skills_to_upsert.append({"skill_name": strength.strip(), "source": "gap_analysis", "category": "technical"})

    if skills_to_upsert:
        try:
            from app.services.global_skills import GlobalSkillsService
            skills_svc = GlobalSkillsService()
            for skill_data in skills_to_upsert:
                try:
                    await skills_svc.upsert_skill(user_id, skill_data)
                except Exception:
                    pass  # Skip individual skill failures
            logger.info("post_gen.skills_extracted", user_id=user_id, count=len(skills_to_upsert))
        except Exception as e:
            logger.warning("post_gen.skills_extraction_failed", error=str(e)[:200])

    # 3. Auto-generate knowledge recommendations based on new gaps
    if "gaps" in requested:
        try:
            from app.services.knowledge_library import KnowledgeLibraryService
            knowledge_svc = KnowledgeLibraryService()
            await knowledge_svc.generate_recommendations(user_id)
            logger.info("post_gen.knowledge_recs_generated", user_id=user_id)
        except Exception as e:
            logger.warning("post_gen.knowledge_recs_failed", error=str(e)[:200])

    # 4. Auto-capture a career snapshot for the analytics timeline
    try:
        from app.services.career_analytics import CareerAnalyticsService
        career_svc = CareerAnalyticsService()
        await career_svc.capture_snapshot(user_id)
        logger.info("post_gen.career_snapshot_captured", user_id=user_id)
    except Exception as e:
        logger.warning("post_gen.career_snapshot_failed", error=str(e)[:200])


async def _sync_document_library(
    sb: Any,
    tables: Dict[str, str],
    *,
    user_id: str,
    application_id: str,
    result: Dict[str, Any],
    requested: set,
) -> None:
    """Populate the document_library table with generated content.

    Idempotent: updates existing entries on re-generation instead of creating duplicates.

    Creates:
      1. Fixed library (persistent, cross-application) — idempotent
      2. Benchmark library (per-application) — idempotent
      3. Tailored documents with ready content from the pipeline
    """
    from app.services.document_library import DocumentLibraryService

    svc = DocumentLibraryService(sb, tables)

    # 1. Ensure the user's fixed library exists (idempotent — skips existing)
    await svc.ensure_fixed_library(user_id)

    # 2. Create benchmark library entries for this application (check for existing first)
    if "benchmark" in requested and result.get("benchmark"):
        existing_bench = await svc.get_documents_by_category(user_id, "benchmark", application_id)
        if not existing_bench:
            await svc.create_benchmark_library(user_id, application_id)

    # 3. Create or update tailored document entries with generated content
    _DOC_MAP = [
        ("cvHtml", "cv", "Tailored CV"),
        ("coverLetterHtml", "cover_letter", "Tailored Cover Letter"),
        ("personalStatementHtml", "personal_statement", "Tailored Personal Statement"),
        ("portfolioHtml", "portfolio", "Portfolio"),
    ]

    # Fetch existing tailored docs for this application to avoid duplicates
    existing_tailored = await svc.get_documents_by_category(user_id, "tailored", application_id)
    existing_tailored_by_type = {d["doc_type"]: d for d in existing_tailored}

    for result_key, doc_type, label in _DOC_MAP:
        html = result.get(result_key) or ""
        if not isinstance(html, str) or not html.strip():
            continue

        existing_doc = existing_tailored_by_type.get(doc_type)
        if existing_doc:
            # Update the existing entry instead of creating a duplicate
            await svc.update_document_content(user_id, existing_doc["id"], html)
        else:
            await svc.create_document(
                user_id=user_id,
                doc_type=doc_type,
                doc_category="tailored",
                label=label,
                application_id=application_id,
                html_content=html,
                status="ready",
                source="planner",
            )

    # 4. If there's a benchmark CV HTML, store it in the benchmark library
    benchmark_cv = result.get("benchmarkCvHtml") or ""
    if isinstance(benchmark_cv, str) and benchmark_cv.strip():
        bench_docs = await svc.get_documents_by_category(user_id, "benchmark", application_id)
        for bd in bench_docs:
            if bd.get("doc_type") == "cv":
                await svc.update_document_content(user_id, bd["id"], benchmark_cv)
                break

    # 5. Populate tailored docs from document pack plan if available
    discovered = result.get("discoveredDocuments") or []
    if isinstance(discovered, list) and discovered:
        planned = []
        for d in discovered:
            if not isinstance(d, dict):
                continue
            dkey = d.get("key") or d.get("doc_type") or ""
            dlabel = d.get("label") or dkey.replace("_", " ").title()
            # Skip types already created above or already in library
            if dkey in ("cv", "cover_letter", "personal_statement", "portfolio"):
                continue
            if dkey in existing_tailored_by_type:
                continue
            planned.append({"key": dkey, "label": dlabel, "metadata": d.get("metadata", {})})
        if planned:
            await svc.create_tailored_documents_from_plan(user_id, application_id, planned)


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
        if job.get("status") in {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}:
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


async def _run_generation_job(job_id: str, user_id: str) -> None:
    """Thin adapter — always delegates to the canonical runtime entrypoint.

    ``_run_generation_job_via_runtime`` is the authoritative execution path.
    This shim exists only so that existing test imports keep working without
    touching every test fixture.  Do NOT add logic here; extend the runtime
    or its helpers instead.
    """
    await _run_generation_job_via_runtime(job_id, user_id)


async def _run_generation_job_inner(job_id: str, user_id: str) -> None:
    """Backward-compatible legacy runner used by tests and compatibility imports.

    Production in-process jobs run via `_run_generation_job_via_runtime`.
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
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "failed",
                "error_message": "Generation job record not found.",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return

    job = job_resp.data[0]
    application_id = str(job.get("application_id") or "")
    requested_modules = _normalize_requested_modules(job.get("requested_modules"))

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", application_id)
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

    event_sequence = 0

    async def emit(event_name: str, payload: Dict[str, Any]) -> None:
        nonlocal event_sequence
        event_sequence += 1
        await _persist_generation_job_event(
            sb,
            TABLES,
            job_id=job_id,
            user_id=user_id,
            application_id=application_id,
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

    async def emit_error(message: str, code: int) -> None:
        await _persist_generation_job_update(
            sb,
            TABLES,
            job_id,
            {
                "status": "cancelled" if code == 499 else "failed",
                "error_message": message,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await emit("error", {"message": message, "code": code})

    if not job_title or not jd_text_val:
        await emit_error(
            "Application is missing job title or job description — please complete the application first",
            400,
        )
        return

    if bool(job.get("cancel_requested")):
        await emit_error("Generation cancelled.", 499)
        return

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
        application_id,
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
    await emit_progress("recon", 1, 8, "Recon is gathering company intelligence…")

    recon_chain = CompanyIntelChain(ai)
    try:
        company_intel = await recon_chain.gather_intel(
            company=company_name,
            job_title=job_title,
            jd_text=jd_text_val,
            on_event=None,
        )
    except Exception:
        company_intel = {"confidence": "low", "data_sources": ["Job description analysis"]}
    await emit_progress("recon_done", 1, 14, "Recon finished gathering public intel ✓")

    await emit_progress("profiling", 2, 18, "Atlas is parsing your resume and building the target benchmark…")
    profiler = RoleProfilerChain(ai)
    benchmark_chain = BenchmarkBuilderChain(ai)
    if resume_text_val.strip():
        user_profile, benchmark_data = await asyncio.gather(
            profiler.parse_resume(resume_text_val),
            benchmark_chain.create_ideal_profile(job_title, company_str, jd_text_val),
        )
    else:
        user_profile = {}
        benchmark_data = await benchmark_chain.create_ideal_profile(job_title, company_str, jd_text_val)
    await emit_progress("profiling_done", 2, 28, "Atlas finished the resume and benchmark analysis ✓")

    await emit_progress("gap_analysis", 3, 38, "Cipher is analyzing skill gaps and keyword misses…")
    gap_chain = GapAnalyzerChain(ai)
    gap_analysis = await gap_chain.analyze_gaps(user_profile, benchmark_data, job_title, company_str)
    await emit_progress("gap_analysis_done", 3, 48, "Cipher finished the gap analysis ✓")

    await emit_progress("documents", 4, 62, "Quill is drafting your tailored documents…")
    doc_chain = DocumentGeneratorChain(ai)
    consultant_chain = CareerConsultantChain(ai)
    validator_chain = ValidatorChain(ai)

    async def safe_call(coro: Any, default: Any) -> Any:
        try:
            return await coro
        except Exception:
            return default

    cv_html, cl_html, ps_html = await asyncio.gather(
        safe_call(doc_chain.generate_tailored_cv(user_profile, benchmark_data, gap_analysis, job_title, company_str), ""),
        safe_call(doc_chain.generate_tailored_cover_letter(user_profile, benchmark_data, gap_analysis, job_title, company_str), ""),
        safe_call(doc_chain.generate_tailored_personal_statement(user_profile, benchmark_data, gap_analysis, job_title, company_str), ""),
    )
    portfolio_html = await safe_call(
        doc_chain.generate_tailored_portfolio(user_profile, benchmark_data, gap_analysis, job_title, company_str),
        "",
    )
    await emit_progress("documents_done", 4, 74, "Quill finished your core documents ✓")

    await emit_progress("portfolio", 5, 82, "Forge is assembling your portfolio proof points…")
    roadmap = await safe_call(consultant_chain.generate_roadmap(user_profile, benchmark_data, gap_analysis), {})
    await emit_progress("portfolio_done", 5, 88, "Forge finished portfolio recommendations ✓")

    await emit_progress("validation", 6, 94, "Sentinel is validating quality and structure…")
    validation = await safe_call(validator_chain.validate_document(cv_html or cl_html or ""), (True, {}))
    validation_payload = validation[1] if isinstance(validation, tuple) and len(validation) > 1 else {}
    await emit_progress("validation_done", 6, 97, "Sentinel quality checks complete ✓")

    await emit_progress("formatting", 7, 99, "Nova is finalizing output formatting…")

    result = {
        "cvHtml": cv_html,
        "coverLetterHtml": cl_html,
        "personalStatementHtml": ps_html,
        "portfolioHtml": portfolio_html,
        "benchmark": benchmark_data,
        "gaps": gap_analysis,
        "learningPlan": roadmap,
        "validation": validation_payload,
        "meta": {
            "company_intel": company_intel,
        },
    }

    await _persist_generation_result_to_application(
        sb,
        TABLES,
        application_row=application_row,
        requested_modules=requested_modules,
        result=result,
        user_id=user_id,
    )

    await _persist_generation_job_update(
        sb,
        TABLES,
        job_id,
        {
            "status": "succeeded",
            "progress": 100,
            "phase": "formatting",
            "message": "Generation complete",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        },
    )
    await _mark_application_generation_finished(
        sb,
        TABLES,
        application_id,
        application_row,
        requested_modules,
        status="succeeded",
    )
    await emit("complete", {"progress": 100, "result": result})


async def _fetch_job_and_application(
    job_id: str,
    user_id: str,
) -> Optional[tuple[Any, Dict[str, Any], Dict[str, Any], str, List[str]]]:
    """Fetch the job row and its owning application for runtime execution."""
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()

    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("id,user_id,application_id,requested_modules,status")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    job_rows = job_resp.data if job_resp else None
    job = job_rows[0] if isinstance(job_rows, list) and job_rows else None
    if not job:
        logger.warning("job_runtime.job_not_found", job_id=job_id, user_id=user_id)
        return None

    if job.get("status") in {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}:
        logger.info("job_runtime.skip_terminal", job_id=job_id, status=job.get("status"))
        return None

    application_id = str(job.get("application_id") or "")
    if not application_id:
        logger.error("job_runtime.missing_application_id", job_id=job_id)
        await _finalize_orphaned_job(job_id, status="failed", error_message="Application not found for job.")
        return None

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    app_rows = app_resp.data if app_resp else None
    app_data = app_rows[0] if isinstance(app_rows, list) and app_rows else None
    if not app_data:
        logger.error("job_runtime.application_not_found", job_id=job_id, application_id=application_id)
        await _finalize_orphaned_job(job_id, status="failed", error_message="Application not found.")
        return None

    requested_modules = _normalize_requested_modules(job.get("requested_modules"))
    return sb, job, app_data, application_id, requested_modules


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

    # Phase A.3 / B.1.2: bridge enriched ContextVar events into the same
    # generation_job_events table the dock listens to.  Without this, the
    # runtime path emits only PipelineEvent rows (progress / detail) and
    # all tool_call / tool_result / cache_hit / evidence_added /
    # policy_decision events fired inside chains go to /dev/null.
    from ai_engine.agent_events import set_event_emitter, reset_event_emitter

    _runtime_event_seq = {"n": 0}

    async def _runtime_emit(event_name: str, payload: Dict[str, Any]) -> None:
        _runtime_event_seq["n"] += 1
        try:
            await _persist_generation_job_event(
                sb, TABLES,
                job_id=job_id, user_id=user_id, application_id=application_id,
                sequence_no=_runtime_event_seq["n"] + 1_000_000,  # offset to avoid collision with sink seq
                event_name=event_name, payload=payload,
            )
        except Exception as persist_err:
            logger.debug(
                "runtime_event_persist_failed",
                event_name=event_name, error=str(persist_err)[:200],
            )

    _emitter_token = set_event_emitter(_runtime_emit)
    try:
        return await _run_generation_job_inner_runtime_body(
            sb, job, app_data, application_id, requested_modules, runtime, job_id, user_id,
        )
    finally:
        try:
            reset_event_emitter(_emitter_token)
        except Exception:
            pass


async def _run_generation_job_inner_runtime_body(
    sb: Any, job: Dict[str, Any], app_data: Dict[str, Any],
    application_id: str, requested_modules: List[str], runtime: Any,
    job_id: str, user_id: str,
) -> None:
    """Inner runtime job body.  Split out so the outer wrapper can manage the
    Phase A.2 emitter binding cleanly via try/finally."""
    from app.core.database import TABLES

    # Mark job as running with full state
    await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .update({
            "status": "running",
            "progress": 1,
            "phase": "initializing",
            "message": "Initializing AI engine…",
            "current_agent": "recon",
            "completed_steps": 0,
            "total_steps": _JOB_TOTAL_STEPS,
            "active_sources_count": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error_message": None,
        })
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

        # Mark job complete via the shared finalisation helper so this path
        # produces the same canonical payload as the orchestrator path
        # above. Critic-flagged runs become "succeeded_with_warnings"
        # automatically; ``doc_pack_plan`` is merged in as an extra field.
        _extra_fields: dict = {}
        if doc_pack_plan:
            _extra_fields["generation_plan"] = doc_pack_plan
        _job_update = finalize_job_status_payload(
            result,
            total_steps=_JOB_TOTAL_STEPS,
            extra_fields=_extra_fields,
        )
        await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .update(_job_update)
            .eq("id", job_id).execute()
        )
        logger.info("job_runtime.complete", job_id=job_id)

    except Exception as e:
        _err_msg = str(e)
        logger.error("job_runtime.failed", job_id=job_id, error=_err_msg[:300])
        await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .update({
                "status": "failed",
                "progress": 0,
                "message": _err_msg[:500],
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
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

    # Try to enqueue to Redis Streams for the dedicated worker process.
    # Falls back to in-process asyncio.create_task when Redis is unavailable.
    try:
        from app.core.queue import enqueue_generation_job

        # enqueue_generation_job is async — schedule it and let the coroutine
        # decide whether Redis accepted the job.
        async def _try_enqueue() -> None:
            enqueued = await enqueue_generation_job(job_id, user_id)
            if enqueued:
                logger.info("generation_job_enqueued", job_id=job_id)
                return
            # Redis unavailable — fall back to in-process
            _start_generation_job_inprocess(job_id, user_id)

        asyncio.create_task(_try_enqueue())
    except Exception:
        # Import or other failure — fall back
        _start_generation_job_inprocess(job_id, user_id)


def _start_generation_job_inprocess(job_id: str, user_id: str) -> None:
    """Execute the generation job in the web process (fallback when no worker)."""
    if job_id in _ACTIVE_GENERATION_TASKS:
        return

    logger.info("generation_job_inprocess_fallback", job_id=job_id)

    # Always use PipelineRuntime-backed execution
    task = asyncio.create_task(_run_generation_job_via_runtime(job_id, user_id))
    _ACTIVE_GENERATION_TASKS[job_id] = task

    def _cleanup(completed_task: asyncio.Task) -> None:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)
        try:
            completed_task.result()
        except asyncio.CancelledError:
            # External cancellation
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
            if status in {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}:
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


# ── Post-generation platform sync (P2-05) ─────────────────────────────

@router.post("/post-hooks/{application_id}")
@limiter.limit("5/minute")
async def trigger_post_generation_hooks(
    request: Request,
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Trigger platform-level sync hooks for a completed application.

    This endpoint is called by the frontend after generation completes to
    ensure global skills, knowledge recommendations, and career snapshots
    are synced — especially useful as a fallback when the automatic hooks
    inside the generation pipeline encounter transient failures.
    """
    validate_uuid(application_id, "application_id")
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Verify application exists and belongs to user
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id,user_id,gaps,benchmark,learning_plan,confirmed_facts,modules")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_row = app_resp.data
    # Build a result dict from the stored application data
    result = {}
    if app_row.get("gaps"):
        result["gaps"] = app_row["gaps"]
    if app_row.get("benchmark"):
        result["benchmark"] = app_row["benchmark"]
    if app_row.get("learning_plan"):
        result["learningPlan"] = app_row["learning_plan"]

    # Only run hooks if the application actually has generated content
    requested = set(result.keys()) | {"gaps"}

    hooks_result = {"synced": []}
    try:
        await _run_post_generation_hooks(
            sb, TABLES,
            user_id=user_id,
            application_id=application_id,
            result=result,
            requested=requested,
            application_row=app_row,
        )
        hooks_result["synced"] = ["skills_gaps", "skills_extraction", "knowledge_recommendations", "career_snapshot"]
        hooks_result["status"] = "completed"
    except Exception as e:
        logger.warning("post_hooks_endpoint_failed", application_id=application_id, error=str(e)[:200])
        hooks_result["status"] = "partial"
        hooks_result["error"] = str(e)[:200]

    return hooks_result


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
        "model_health": _get_model_health_summary(),
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
    if orig_job.get("status") not in {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}:
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
        try:
            resp = await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_jobs"])
                .select("id,user_id,status,application_id,requested_modules,recovery_attempts")
                .in_("status", ["running", "queued"])
                .execute()
            )
        except Exception:
            # recovery_attempts column may not exist yet — fall back
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

            # Fallback: re-queue the job so it auto-restarts instead of
            # blanket-failing.  The user sees "Resuming…" instead of a dead error.
            # We cap retry attempts to prevent infinite restart loops.
            recovery_attempts = (job.get("recovery_attempts") or 0) + 1
            max_recovery = 3

            if recovery_attempts <= max_recovery:
                try:
                    await asyncio.to_thread(
                        lambda jid=job_id, ra=recovery_attempts: sb.table(TABLES["generation_jobs"])
                        .update({
                            "status": "queued",
                            "progress": 0,
                            "error_message": None,
                            "recovery_attempts": ra,
                            "finished_at": None,
                        })
                        .eq("id", jid)
                        .execute()
                    )
                except Exception:
                    # recovery_attempts column may not exist — update without it
                    await asyncio.to_thread(
                        lambda jid=job_id: sb.table(TABLES["generation_jobs"])
                        .update({
                            "status": "queued",
                            "progress": 0,
                            "error_message": None,
                            "finished_at": None,
                        })
                        .eq("id", jid)
                        .execute()
                    )
                # Actually restart the job in-process
                _user_id = job.get("user_id", "")
                _start_generation_job(job_id, _user_id)
                logger.info(
                    "job_recovery.requeued",
                    job_id=job_id,
                    attempt=recovery_attempts,
                )
                recovered_count += 1
                continue

            # Exceeded max retries — fail permanently with clear message
            fail_msg = "Generation failed after multiple server restarts. Please click Regenerate to try again."
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
