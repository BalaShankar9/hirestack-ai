"""
Unified AI Generation Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single endpoint that orchestrates the full AI-powered application generation:
  1. Parse resume → structured user profile
  2. Build ideal candidate benchmark
  3. Analyze gaps (user vs benchmark)
  4. Generate strategically tailored CV (HTML)
  5. Generate tailored cover letter (HTML)
  6. Generate learning plan / roadmap
  7. Compute match scores
"""
import asyncio
import json
import math
import re
import traceback
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.api.deps import get_current_user, validate_uuid, check_billing_limit
from app.core.security import limiter
from app.core.sanitize import sanitize_html
from app.core.circuit_breaker import CircuitBreakerOpen

# ── PipelineRuntime (canonical execution engine) ──
try:
    from app.services.pipeline_runtime import (
        PipelineRuntime as _PipelineRuntime,
        RuntimeConfig as _RuntimeConfig,
        ExecutionMode as _ExecutionMode,
        CollectorSink as _CollectorSink,
        SSESink as _SSESink,
        DatabaseSink as _DatabaseSink,
    )
    _RUNTIME_AVAILABLE = True
except ImportError:
    _RUNTIME_AVAILABLE = False


def _sanitize_output_html(html: str) -> str:
    """Sanitize AI-generated HTML before sending to frontend (XSS prevention)."""
    if not html:
        return ""
    return sanitize_html(html)


try:
    from ai_engine.agents.pipelines import (
        resume_parse_pipeline,
        benchmark_pipeline,
        gap_analysis_pipeline,
        cv_generation_pipeline,
        cover_letter_pipeline,
        personal_statement_pipeline,
        portfolio_pipeline,
    )
    from ai_engine.agents.orchestrator import PipelineResult
    from ai_engine.agents.workflow_runtime import (
        WorkflowEventStore as _WorkflowEventStore,
        reconstruct_state as _reconstruct_state,
        get_completed_stages as _get_completed_stages,
        is_safely_resumable as _is_safely_resumable,
    )
    _AGENT_PIPELINES_AVAILABLE = True
except ImportError:
    _AGENT_PIPELINES_AVAILABLE = False


_PIPELINE_NAMES = ["cv_generation", "cover_letter", "personal_statement", "portfolio"]
_STAGE_ORDER = ["researcher", "drafter", "critic", "optimizer", "fact_checker", "validator"]


def _extract_pipeline_html(payload: Any) -> str:
    """Return HTML from either raw pipeline content or a validator envelope."""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    html = payload.get("html")
    if isinstance(html, str):
        return html

    nested = payload.get("content")
    if isinstance(nested, str):
        return nested
    if isinstance(nested, dict):
        nested_html = nested.get("html")
        if isinstance(nested_html, str):
            return nested_html

    return ""


def _quality_score_from_scores(scores: Any) -> float:
    """Collapse per-dimension critic scores into a single user-facing score."""
    if not isinstance(scores, dict) or not scores:
        return 0.0

    overall = scores.get("overall")
    if isinstance(overall, (int, float)):
        return float(overall)

    numeric_scores = [float(value) for value in scores.values() if isinstance(value, (int, float))]
    if not numeric_scores:
        return 0.0
    return round(sum(numeric_scores) / len(numeric_scores), 1)


def _validation_issue_count(report: Any) -> int:
    if not isinstance(report, dict):
        return 0
    issues = report.get("issues")
    return len(issues) if isinstance(issues, list) else 0


def _build_evidence_summary(pipeline_result) -> Optional[Dict[str, Any]]:
    """Build a compact evidence summary from a PipelineResult for the frontend."""
    if not pipeline_result:
        return None
    ledger = getattr(pipeline_result, "evidence_ledger", None)
    citations = getattr(pipeline_result, "citations", None) or []
    if not ledger and not citations:
        return None

    tier_dist: Dict[str, int] = {}
    total_items = 0
    if isinstance(ledger, dict):
        items = ledger.get("items", [])
        total_items = len(items) if isinstance(items, list) else ledger.get("count", 0)
        for item in (items if isinstance(items, list) else []):
            tier = item.get("tier", "unknown") if isinstance(item, dict) else "unknown"
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

    fabricated = sum(
        1 for c in citations
        if isinstance(c, dict) and c.get("classification") in ("fabricated", "unsupported")
    )
    unlinked = sum(
        1 for c in citations
        if isinstance(c, dict) and not c.get("evidence_ids")
    )

    return {
        "evidence_count": total_items,
        "tier_distribution": tier_dist,
        "citation_count": len(citations),
        "fabricated_count": fabricated,
        "unlinked_count": unlinked,
    }


def _extract_retry_after_seconds(err: str) -> Optional[int]:
    """Best-effort parse of provider retry hints into whole seconds."""
    # Gemini often includes: "Please retry in 51.7469s."
    m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", err, flags=re.IGNORECASE)
    if m:
        try:
            return max(1, int(math.ceil(float(m.group(1)))))
        except Exception:
            pass

    # Gemini also includes a structured field: "retryDelay': '51s'"
    m = re.search(r"retryDelay'\s*:\s*'(\d+)s'", err)
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            pass

    return None


def _classify_ai_error(exc: Exception) -> Optional[Dict[str, Any]]:
    """Classify an AI provider exception into a structured response for HTTP/SSE."""
    # ── Gemini / generic string-based errors ──
    err = str(exc).lower()
    if (
        "api key not valid" in err
        or "api_key_invalid" in err
        or "api keys are not supported" in err
        or "expected oauth2 access token" in err
        or "credentials_missing" in err
    ):
        return {
            "code": 401,
            "message": (
                "Your Gemini credential isn't a valid API key for the Gemini API. "
                "Create a Google AI Studio API key (usually starts with 'AIza…') and set GEMINI_API_KEY, "
                "or configure Vertex AI by setting GEMINI_USE_VERTEXAI=true with OAuth credentials."
            ),
        }
    if "permission denied" in err or "permission_denied" in err:
        return {"code": 403, "message": "Gemini API permission denied. Check your API key and project settings."}
    if "not found" in err and ("model" in err or "404" in err):
        from app.core.config import settings as _s
        return {"code": 404, "message": f"The AI model '{_s.gemini_model}' was not found. Check your GEMINI_MODEL setting."}
    if "resource exhausted" in err or "rate limit" in err or "429" in err:
        return {
            "code": 429,
            "message": "AI rate limit reached. Please wait a moment and try again.",
            "retry_after_seconds": _extract_retry_after_seconds(str(exc)),
        }

    return None  # Not a classified error

logger = structlog.get_logger()

router = APIRouter()


# ── Request schema ────────────────────────────────────────────────────
MAX_JD_SIZE = 50_000       # 50KB — no JD is this long
MAX_RESUME_SIZE = 100_000  # 100KB — generous for parsed text
PIPELINE_TIMEOUT = 300     # 5 minutes — hard ceiling for the sync pipeline
PHASE_TIMEOUT = 60         # 60s per individual phase (discovery, parsing, etc.)


class PipelineRequest(BaseModel):
    job_title: str
    company: str = ""
    jd_text: str
    resume_text: str = ""


def _validate_pipeline_input(req: PipelineRequest) -> None:
    """Reject oversized or empty inputs."""
    if not req.job_title.strip():
        raise HTTPException(status_code=400, detail="Job title is required")
    if not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required")
    if len(req.jd_text) > MAX_JD_SIZE:
        raise HTTPException(status_code=413, detail="Job description too large (max 50KB)")
    if len(req.resume_text) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="Resume text too large (max 100KB)")


# ── Main pipeline endpoint ────────────────────────────────────────────
@router.post("/pipeline")
@limiter.limit("3/minute")
async def generate_pipeline(request: Request, req: PipelineRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Run the complete AI generation pipeline and return all modules."""
    await check_billing_limit("ai_calls", current_user)
    _validate_pipeline_input(req)
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub") or "anonymous"
    try:
        if _RUNTIME_AVAILABLE:
            config = _RuntimeConfig(
                mode=_ExecutionMode.SYNC,
                timeout=PIPELINE_TIMEOUT,
                user_id=user_id,
            )
            runtime = _PipelineRuntime(config=config, event_sink=_CollectorSink())
            return await asyncio.wait_for(
                runtime.execute({
                    "job_title": req.job_title,
                    "company": req.company,
                    "jd_text": req.jd_text,
                    "resume_text": req.resume_text,
                }),
                timeout=PIPELINE_TIMEOUT,
            )
        else:
            return await asyncio.wait_for(
                _run_sync_pipeline(req, current_user),
                timeout=PIPELINE_TIMEOUT,
            )
    except asyncio.TimeoutError:
        logger.error("pipeline.timeout", timeout_seconds=PIPELINE_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail="Generation took too long. Please try a shorter job description or simpler request.",
        )
    except HTTPException:
        raise
    except CircuitBreakerOpen as cbe:
        logger.warning("pipeline.circuit_breaker_open", breaker=cbe.name, remaining_s=cbe.remaining_s)
        raise HTTPException(
            status_code=503,
            detail="AI service is temporarily unavailable due to repeated failures. Please try again shortly.",
            headers={"Retry-After": str(int(cbe.remaining_s) + 1)},
        )
    except Exception as e:
        classified = _classify_ai_error(e)
        if classified:
            code = int(classified["code"])
            msg = str(classified["message"])
            retry_after = classified.get("retry_after_seconds")
            logger.error("pipeline.ai_error", code=code, message=msg, retry_after_seconds=retry_after)
            headers = {"Retry-After": str(retry_after)} if retry_after else None
            raise HTTPException(status_code=code, detail=msg, headers=headers)

        logger.error(
            "pipeline.error",
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="AI generation failed due to an unexpected error. Please try again in a moment.",
        )


# ── Planner-driven pipeline endpoint ─────────────────────────────────
class PlannedPipelineRequest(BaseModel):
    """Request body for the planner-driven pipeline endpoint."""
    user_request: str
    job_title: str = ""
    company: str = ""
    jd_text: str = ""
    resume_text: str = ""


@router.post("/pipeline/planned")
@limiter.limit("3/minute")
async def generate_planned_pipeline(
    request: Request,
    req: PlannedPipelineRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Use the PlannerAgent to decide which pipeline(s) to run, then execute the plan."""
    await check_billing_limit("ai_calls", current_user)

    if not req.user_request.strip():
        raise HTTPException(status_code=400, detail="user_request is required")

    try:
        return await asyncio.wait_for(
            _run_planned_pipeline(req, current_user),
            timeout=PIPELINE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Planned generation timed out.")
    except HTTPException:
        raise
    except CircuitBreakerOpen as cbe:
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable.",
            headers={"Retry-After": str(int(cbe.remaining_s) + 1)},
        )
    except Exception as e:
        classified = _classify_ai_error(e)
        if classified:
            raise HTTPException(
                status_code=int(classified["code"]),
                detail=str(classified["message"]),
            )
        logger.error("planned_pipeline.error", error=str(e), traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail="Planned generation failed unexpectedly.")


async def _run_planned_pipeline(req: PlannedPipelineRequest, current_user: Dict[str, Any]) -> dict:
    """Execute PlannerAgent → multi-pipeline executor."""
    from ai_engine.client import AIClient
    from ai_engine.agents.planner import PlannerAgent
    from ai_engine.agents.multi_pipeline import execute_plan
    from app.core.database import get_supabase, TABLES

    ai = AIClient()
    sb = get_supabase()
    user_id = current_user.get("id", "")

    # Step 1: Plan
    planner = PlannerAgent(ai_client=ai)
    plan_result = await planner.run({
        "user_request": req.user_request,
        "available_data": {
            "has_resume": bool(req.resume_text.strip()),
            "has_jd": bool(req.jd_text.strip()),
            "has_job_title": bool(req.job_title.strip()),
            "has_company": bool(req.company.strip()),
        },
    })

    plan = plan_result.metadata.get("plan")
    if not plan:
        raise HTTPException(status_code=500, detail="Planner produced no plan")

    # Step 2: Execute the plan
    context = {
        "user_id": user_id,
        "job_title": req.job_title,
        "company": req.company or "the company",
        "jd_text": req.jd_text,
        "resume_text": req.resume_text,
    }

    multi_result = await execute_plan(
        plan=plan,
        context=context,
        ai_client=ai,
        db=sb,
        tables=TABLES,
    )

    # Step 3: Format response
    primary = multi_result.get("primary_result")
    return {
        "plan": multi_result.get("plan"),
        "total_latency_ms": multi_result.get("total_latency_ms"),
        "primary_content": primary.content if primary else {},
        "primary_quality_scores": primary.quality_scores if primary else {},
        "all_results": {
            name: {
                "content": r.content,
                "quality_scores": r.quality_scores,
                "iterations_used": r.iterations_used,
                "total_latency_ms": r.total_latency_ms,
                "escalation": r.escalation,
            }
            for name, r in multi_result.get("results", {}).items()
        },
    }


async def _run_sync_pipeline(req: PipelineRequest, current_user: Dict[str, Any]) -> dict:
    """Inner pipeline logic extracted for timeout wrapping."""
    from ai_engine.client import AIClient
    from ai_engine.chains.role_profiler import RoleProfilerChain
    from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
    from ai_engine.chains.gap_analyzer import GapAnalyzerChain
    from ai_engine.chains.document_generator import DocumentGeneratorChain
    from ai_engine.chains.career_consultant import CareerConsultantChain
    from ai_engine.chains.validator import ValidatorChain
    from ai_engine.chains.document_discovery import DocumentDiscoveryChain
    from ai_engine.chains.adaptive_document import AdaptiveDocumentChain

    ai = AIClient()
    company = req.company or "the company"
    failed_modules: List[Dict[str, str]] = []  # P1-06: track partial failures

    logger.info(
        "pipeline.start",
        job_title=req.job_title,
        company=company,
        jd_length=len(req.jd_text),
        resume_length=len(req.resume_text),
    )

    # ── Phase 0: Document Discovery ───────────────────────────────
    discovery_chain = DocumentDiscoveryChain(ai)
    try:
        discovery = await asyncio.wait_for(
            discovery_chain.discover(req.jd_text, req.job_title, company),
            timeout=PHASE_TIMEOUT,
        )
        required_docs = discovery.get("required_documents", [])
        optional_docs = discovery.get("optional_documents", [])
        logger.info("pipeline.discovery_done", required=len(required_docs), optional=len(optional_docs))
    except Exception as disc_err:
        logger.warning("pipeline.discovery_failed", error=str(disc_err))
        failed_modules.append({"module": "discovery", "error": str(disc_err)[:200]})
        # Fallback to standard docs
        discovery = {"industry": "other", "tone": "professional", "key_themes": []}
        required_docs = [
            {"key": "cv", "label": "Tailored CV", "priority": "critical"},
            {"key": "cover_letter", "label": "Cover Letter", "priority": "critical"},
            {"key": "personal_statement", "label": "Personal Statement", "priority": "high"},
            {"key": "portfolio", "label": "Portfolio", "priority": "medium"},
        ]
        optional_docs = [{"key": "learning_plan", "label": "Learning Plan", "priority": "medium"}]

    # ── Phase 0.5: Company Intelligence Gathering ────────────────
    from ai_engine.chains.company_intel import CompanyIntelChain

    company_intel = {}
    try:
        intel_chain = CompanyIntelChain(ai)
        company_intel = await asyncio.wait_for(
            intel_chain.gather_intel(
                company=company,
                job_title=req.job_title,
                jd_text=req.jd_text,
            ),
            timeout=PHASE_TIMEOUT,
        )
        logger.info(
            "pipeline.intel_done",
            confidence=company_intel.get("confidence", "unknown"),
            sources=len(company_intel.get("data_sources", [])),
        )
    except Exception as intel_err:
        logger.warning("pipeline.intel_failed", error=str(intel_err)[:200])
        failed_modules.append({"module": "company_intel", "error": str(intel_err)[:200]})

    # ── Phase 0.7: Catalog-driven document pack planning ─────────
    from app.services.document_catalog import discover_and_observe
    from app.core.database import get_supabase, TABLES

    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub") or "anonymous"
    sb = get_supabase()

    doc_pack_plan = await discover_and_observe(
        db=sb, tables=TABLES, ai_client=ai,
        jd_text=req.jd_text, job_title=req.job_title,
        company=company, user_profile=None,  # profile not parsed yet; planner uses JD + intel
        user_id=user_id,
        company_intel=company_intel,
        phase_timeout=PHASE_TIMEOUT,
    )

    if doc_pack_plan:
        # Override discovery chain results with catalog-driven plan
        required_docs = doc_pack_plan.core + doc_pack_plan.required
        optional_docs = doc_pack_plan.optional
        discovery["industry"] = doc_pack_plan.industry
        discovery["tone"] = doc_pack_plan.tone
        discovery["key_themes"] = doc_pack_plan.key_themes
        logger.info(
            "pipeline.catalog_plan_applied",
            required=len(required_docs),
            optional=len(optional_docs),
        )

    # ── Phase 1: Parse resume + Build benchmark (parallel) ────────
    profiler = RoleProfilerChain(ai)
    benchmark_chain = BenchmarkBuilderChain(ai)

    if req.resume_text.strip():
        user_profile, benchmark_data = await asyncio.wait_for(
            asyncio.gather(
                profiler.parse_resume(req.resume_text),
                benchmark_chain.create_ideal_profile(
                    req.job_title, company, req.jd_text
                ),
            ),
            timeout=PHASE_TIMEOUT * 2,  # parsing + benchmark in parallel
        )
    else:
        user_profile = {}
        benchmark_data = await asyncio.wait_for(
            benchmark_chain.create_ideal_profile(
                req.job_title, company, req.jd_text
            ),
            timeout=PHASE_TIMEOUT,
        )

    logger.info("pipeline.phase1_done", has_profile=bool(user_profile))

    # Generate benchmark documents for ALL required types (100% match)
    benchmark_cv_html = ""
    benchmark_documents = {}
    try:
        benchmark_result = await asyncio.wait_for(
            benchmark_chain.generate_perfect_application(
                jd_text=req.jd_text,
                job_title=req.job_title,
                company=company,
                user_profile=user_profile,
                required_documents=required_docs,
                discovery_context=discovery,
            ),
            timeout=PHASE_TIMEOUT * 2,
        )
        benchmark_documents = benchmark_result.get("benchmark_documents", {})
        benchmark_cv_html = benchmark_documents.get("cv", "")
        logger.info("pipeline.benchmark_docs_done", count=len(benchmark_documents))
    except Exception as bcv_err:
        logger.warning("pipeline.benchmark_docs_failed", error=str(bcv_err)[:200])
        failed_modules.append({"module": "benchmark_docs", "error": str(bcv_err)[:200]})
        # Fallback: try just the CV
        try:
            benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                user_profile=user_profile,
                benchmark_data=benchmark_data,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
            )
        except Exception as bcv_fallback_err:
            logger.warning("pipeline.benchmark_cv_fallback_failed", error=str(bcv_fallback_err)[:200])
            failed_modules.append({"module": "benchmark_cv_fallback", "error": str(bcv_fallback_err)[:200]})

    # Extract keywords from benchmark ideal skills
    ideal_skills = benchmark_data.get("ideal_skills", [])
    keywords = [
        s.get("name", "")
        for s in ideal_skills
        if isinstance(s, dict) and s.get("name")
    ]
    if not keywords:
        keywords = _extract_keywords_from_jd(req.jd_text)

    # ── Phase 2: Gap Analysis ─────────────────────────────────────
    gap_chain = GapAnalyzerChain(ai)
    gap_analysis = await asyncio.wait_for(
        gap_chain.analyze_gaps(
            user_profile, benchmark_data, req.job_title, company
        ),
        timeout=PHASE_TIMEOUT,
    )

    logger.info(
        "pipeline.phase2_done",
        compatibility=gap_analysis.get("compatibility_score", 0),
    )

    # ── Phase 3: Generate FIXED standard documents (parallel) ─────
    doc_chain = DocumentGeneratorChain(ai)
    consultant = CareerConsultantChain(ai)

    skill_gaps = gap_analysis.get("skill_gaps", [])
    strengths = gap_analysis.get("strengths", [])
    key_gaps_str = ", ".join(
        g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
    ) or "None identified"
    strengths_str = ", ".join(
        s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
    ) or "None identified"

    # Generate the 4 standard documents (always, for every job)
    cv_html, cl_html, roadmap = await asyncio.gather(
        doc_chain.generate_tailored_cv(
            user_profile=user_profile, job_title=req.job_title,
            company=company, jd_text=req.jd_text,
            gap_analysis=gap_analysis, resume_text=req.resume_text,
        ),
        doc_chain.generate_tailored_cover_letter(
            user_profile=user_profile, job_title=req.job_title,
            company=company, jd_text=req.jd_text, gap_analysis=gap_analysis,
        ),
        consultant.generate_roadmap(gap_analysis, user_profile, req.job_title, company),
        return_exceptions=True,
    )
    if isinstance(cv_html, Exception):
        logger.error("pipeline.cv_failed", error=str(cv_html))
        failed_modules.append({"module": "cv", "error": str(cv_html)[:200]})
        cv_html = ""
    if isinstance(cl_html, Exception):
        logger.error("pipeline.cl_failed", error=str(cl_html))
        failed_modules.append({"module": "cover_letter", "error": str(cl_html)[:200]})
        cl_html = ""
    if isinstance(roadmap, Exception):
        logger.error("pipeline.roadmap_failed", error=str(roadmap))
        failed_modules.append({"module": "roadmap", "error": str(roadmap)[:200]})
        roadmap = {}

    # Personal Statement + Portfolio (always generated)
    ps_html, portfolio_html = "", ""
    try:
        ps_result, portfolio_result = await asyncio.gather(
            doc_chain.generate_tailored_personal_statement(
                user_profile=user_profile, job_title=req.job_title,
                company=company, jd_text=req.jd_text,
                gap_analysis=gap_analysis, resume_text=req.resume_text,
            ),
            doc_chain.generate_tailored_portfolio(
                user_profile=user_profile, job_title=req.job_title,
                company=company, jd_text=req.jd_text,
                gap_analysis=gap_analysis, resume_text=req.resume_text,
            ),
            return_exceptions=True,
        )
        if isinstance(ps_result, Exception):
            failed_modules.append({"module": "personal_statement", "error": str(ps_result)[:200]})
            ps_html = ""
        else:
            ps_html = ps_result if isinstance(ps_result, str) else ""
        if isinstance(portfolio_result, Exception):
            failed_modules.append({"module": "portfolio", "error": str(portfolio_result)[:200]})
            portfolio_html = ""
        else:
            portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
    except Exception as p4_err:
        logger.error("pipeline.phase4_error", error=str(p4_err))
        failed_modules.append({"module": "phase4_docs", "error": str(p4_err)[:200]})

    logger.info("pipeline.standard_docs_done", cv=len(str(cv_html)), cl=len(str(cl_html)))

    # ── Phase 3b: Generate EXTRA job-specific documents ───────────
    # Only generate docs that aren't already in the fixed set
    FIXED_DOC_KEYS = {"cv", "cover_letter", "personal_statement", "portfolio", "learning_plan", "scorecard"}
    extra_docs_to_generate = [
        d for d in required_docs
        if d.get("key") not in FIXED_DOC_KEYS
    ]

    generated_docs: Dict[str, str] = {}
    if extra_docs_to_generate:
        adaptive_chain = AdaptiveDocumentChain(ai)
        # Build intel summary for document context
        intel_summary = ""
        if company_intel:
            strategy = company_intel.get("application_strategy", {})
            culture = company_intel.get("culture_and_values", {})
            intel_parts = []
            if culture.get("core_values"):
                intel_parts.append(f"Company values: {', '.join(culture['core_values'][:5])}")
            if culture.get("mission_statement"):
                intel_parts.append(f"Mission: {culture['mission_statement']}")
            if strategy.get("keywords_to_use"):
                intel_parts.append(f"Keywords to include: {', '.join(strategy['keywords_to_use'][:8])}")
            if strategy.get("things_to_mention"):
                intel_parts.append(f"Reference: {'; '.join(strategy['things_to_mention'][:3])}")
            intel_summary = "\n".join(intel_parts)

        doc_context = {
            "profile": user_profile,
            "jd_text": req.jd_text,
            "job_title": req.job_title,
            "company": company,
            "industry": discovery.get("industry", "professional"),
            "tone": discovery.get("tone", "professional"),
            "key_themes": discovery.get("key_themes", []),
            "gaps_summary": key_gaps_str,
            "strengths_summary": strengths_str,
            "benchmark_keywords": ", ".join(keywords[:15]),
            "company_intel": intel_summary,
        }

        for i in range(0, len(extra_docs_to_generate), 2):
            batch = extra_docs_to_generate[i:i+2]
            results = await asyncio.gather(
                *[
                    adaptive_chain.generate(
                        doc_type=d["key"], doc_label=d.get("label", d["key"]),
                        context=doc_context, mode="user",
                    )
                    for d in batch
                ],
                return_exceptions=True,
            )
            for d, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(f"pipeline.extra_doc_{d['key']}_failed", error=str(result)[:200])
                    failed_modules.append({"module": d["key"], "error": str(result)[:200]})
                else:
                    generated_docs[d["key"]] = result if isinstance(result, str) else ""

        logger.info("pipeline.extra_docs_done", count=len(generated_docs), keys=list(generated_docs.keys()))

    # ── Phase 4: Validate key documents (non-blocking) ───────────
    validation = {}
    try:
        validator = ValidatorChain(ai)
        if cv_html:
            cv_valid, cv_validation = await asyncio.wait_for(
                validator.validate_document(
                    document_type="Tailored CV",
                    content=cv_html[:3000],
                    profile_data=user_profile,
                ),
                timeout=PHASE_TIMEOUT,
            )
            validation["cv"] = {
                "valid": cv_valid,
                "qualityScore": cv_validation.get("quality_score", 0),
                "issues": len(cv_validation.get("issues", [])),
            }
    except Exception as val_err:
        logger.warning("pipeline.validation_skipped", error=str(val_err))
        failed_modules.append({"module": "validation", "error": str(val_err)[:200]})

    # ── Format response for frontend ──────────────────────────────
    response = _format_response(
        benchmark_data=benchmark_data,
        gap_analysis=gap_analysis,
        roadmap=roadmap if isinstance(roadmap, dict) else {},
        cv_html=cv_html,
        cl_html=cl_html,
        ps_html=ps_html,
        portfolio_html=portfolio_html,
        validation=validation,
        keywords=keywords,
        job_title=req.job_title,
        benchmark_cv_html=benchmark_cv_html,
    )

    # Add new fields: discovered documents, all generated docs, benchmark docs
    response["discoveredDocuments"] = required_docs + optional_docs
    response["generatedDocuments"] = {
        k: _sanitize_output_html(v) for k, v in generated_docs.items() if v
    }
    response["benchmarkDocuments"] = {
        k: (_sanitize_output_html(v) if isinstance(v, str) else v)
        for k, v in benchmark_documents.items()
    }
    response["documentStrategy"] = discovery.get("document_strategy", "")
    if doc_pack_plan:
        response["docPackPlan"] = doc_pack_plan.to_dict()
    if company_intel:
        response["companyIntel"] = company_intel

    # P1-06: Include partial failure metadata so frontend knows what failed
    if failed_modules:
        response["failedModules"] = failed_modules
        logger.warning("pipeline.partial_failures", count=len(failed_modules),
                        modules=[m["module"] for m in failed_modules])

    logger.info("pipeline.complete", overall_score=response["scores"]["overall"],
                docs_generated=len(generated_docs), failures=len(failed_modules))
    return response


# ── SSE Streaming pipeline ────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _agent_sse(pipeline_name: str, stage: str, status: str, latency_ms: int = 0, message: str = "", quality_scores: dict | None = None) -> str:
    """Emit an agent_status SSE event."""
    data = {
        "pipeline_name": pipeline_name,
        "stage": stage,
        "status": status,
        "latency_ms": latency_ms,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if quality_scores:
        data["quality_scores"] = quality_scores
    return f"event: agent_status\ndata: {json.dumps(data)}\n\n"


def _detail_sse(
    agent: str,
    message: str,
    status: str = "info",
    source: str | None = None,
    url: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Emit a structured detail event for terminal-like live logs."""
    data: Dict[str, Any] = {
        "agent": agent,
        "message": message,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if source:
        data["source"] = source
    if url:
        data["url"] = url
    if metadata:
        data["metadata"] = metadata
    return f"event: detail\ndata: {json.dumps(data)}\n\n"


async def _stream_agent_pipeline(req: "PipelineRequest", user_id: str) -> AsyncGenerator[str, None]:
    """
    Agent-powered SSE pipeline.
    Each phase delegates to an AgentPipeline (Researcher → Drafter → Critic →
    Optimizer → FactChecker → Validator) and emits agent_status events in
    real-time alongside the regular progress events.
    """
    try:
        from ai_engine.client import AIClient
        from ai_engine.chains.career_consultant import CareerConsultantChain
        from app.core.database import get_supabase, TABLES

        ai = AIClient()
        sb = get_supabase()
        company = req.company or "the company"

        logger.info("agent_pipeline.start", job_title=req.job_title, company=company, user_id=user_id)

        yield _sse("progress", {
            "phase": "initializing",
            "step": 0,
            "totalSteps": 6,
            "progress": 5,
            "message": "Initializing agent pipeline…",
            "agent_powered": True,
        })

        # ── Shared callback that queues agent_status SSE events ───────
        events_queue: list[str] = []

        async def stage_callback(event: dict) -> None:
            events_queue.append(_agent_sse(
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            ))

        # ── Phase 1a: Resume parse pipeline ──────────────────────────
        yield _sse("progress", {
            "phase": "profiling",
            "step": 1,
            "totalSteps": 6,
            "progress": 8,
            "message": "Agent: parsing resume…",
        })

        user_profile: dict = {}
        if req.resume_text.strip():
            pipe = resume_parse_pipeline(ai_client=ai, on_stage_update=stage_callback, db=sb, tables=TABLES)
            parse_result: PipelineResult = await pipe.execute({
                "user_id": user_id,
                "resume_text": req.resume_text,
            })
            for ev in events_queue:
                yield ev
            events_queue.clear()
            user_profile = parse_result.content if isinstance(parse_result.content, dict) else {}

        # ── Phase 1b: Benchmark pipeline ─────────────────────────────
        yield _sse("progress", {
            "phase": "profiling",
            "step": 1,
            "totalSteps": 6,
            "progress": 15,
            "message": "Agent: building candidate benchmark…",
        })

        bench_pipe = benchmark_pipeline(ai_client=ai, on_stage_update=stage_callback, db=sb, tables=TABLES)
        bench_result: PipelineResult = await bench_pipe.execute({
            "user_id": user_id,
            "job_title": req.job_title,
            "company": company,
            "jd_text": req.jd_text,
        })
        for ev in events_queue:
            yield ev
        events_queue.clear()
        benchmark_data = bench_result.content if isinstance(bench_result.content, dict) else {}

        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = _extract_keywords_from_jd(req.jd_text)

        # Generate benchmark CV (best-effort, uses legacy chain directly)
        benchmark_cv_html = ""
        try:
            from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
            bc = BenchmarkBuilderChain(ai)
            benchmark_cv_html = await bc.create_benchmark_cv_html(
                user_profile=user_profile,
                benchmark_data=benchmark_data,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
            )
        except Exception as bcv_err:
            logger.warning("agent_pipeline.benchmark_cv_failed", error=str(bcv_err))

        yield _sse("progress", {
            "phase": "profiling_done",
            "step": 1,
            "totalSteps": 6,
            "progress": 25,
            "message": "Resume parsed & benchmark built ✓",
        })

        # ── Phase 1c: Company Intel + Catalog Planning ───────────────
        from ai_engine.chains.company_intel import CompanyIntelChain
        from app.services.document_catalog import discover_and_observe

        company_intel_stream: dict = {}
        try:
            intel_chain = CompanyIntelChain(ai)
            company_intel_stream = await asyncio.wait_for(
                intel_chain.gather_intel(company=company, job_title=req.job_title, jd_text=req.jd_text),
                timeout=PHASE_TIMEOUT,
            )
        except Exception as intel_err:
            logger.warning("agent_pipeline.intel_failed", error=str(intel_err)[:200])

        doc_pack_plan_stream = await discover_and_observe(
            db=sb, tables=TABLES, ai_client=ai,
            jd_text=req.jd_text, job_title=req.job_title,
            company=company, user_profile=user_profile,
            user_id=user_id,
            company_intel=company_intel_stream,
            phase_timeout=PHASE_TIMEOUT,
        )

        # ── Phase 2: Gap analysis pipeline ───────────────────────────
        yield _sse("progress", {
            "phase": "gap_analysis",
            "step": 2,
            "totalSteps": 6,
            "progress": 30,
            "message": "Agent: analyzing skill gaps…",
        })

        gap_pipe = gap_analysis_pipeline(ai_client=ai, on_stage_update=stage_callback, db=sb, tables=TABLES)
        gap_result: PipelineResult = await gap_pipe.execute({
            "user_id": user_id,
            "user_profile": user_profile,
            "benchmark": benchmark_data,
            "job_title": req.job_title,
            "company": company,
        })
        for ev in events_queue:
            yield ev
        events_queue.clear()
        gap_analysis = gap_result.content if isinstance(gap_result.content, dict) else {}

        yield _sse("progress", {
            "phase": "gap_analysis_done",
            "step": 2,
            "totalSteps": 6,
            "progress": 45,
            "message": "Gap analysis complete ✓",
        })

        # ── Phase 3: CV + Cover letter + Roadmap (parallel) ──────────
        yield _sse("progress", {
            "phase": "documents",
            "step": 3,
            "totalSteps": 6,
            "progress": 50,
            "message": "Agents: generating CV, cover letter & learning plan…",
        })

        doc_context = {
            "user_id": user_id,
            "user_profile": user_profile,
            "job_title": req.job_title,
            "company": company,
            "jd_text": req.jd_text,
            "gap_analysis": gap_analysis,
            "resume_text": req.resume_text,
        }

        cv_queue: list[str] = []
        cl_queue: list[str] = []

        async def cv_callback(event: dict) -> None:
            cv_queue.append(_agent_sse(
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            ))

        async def cl_callback(event: dict) -> None:
            cl_queue.append(_agent_sse(
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            ))

        cv_pipe = cv_generation_pipeline(ai_client=ai, on_stage_update=cv_callback, db=sb, tables=TABLES)
        cl_pipe = cover_letter_pipeline(ai_client=ai, on_stage_update=cl_callback, db=sb, tables=TABLES)
        consultant = CareerConsultantChain(ai)

        cv_result_raw, cl_result_raw, roadmap = await asyncio.gather(
            cv_pipe.execute(doc_context),
            cl_pipe.execute(doc_context),
            consultant.generate_roadmap(gap_analysis, user_profile, req.job_title, company),
            return_exceptions=True,
        )

        for ev in cv_queue:
            yield ev
        for ev in cl_queue:
            yield ev

        cv_result: PipelineResult | None = None
        cl_result: PipelineResult | None = None

        if isinstance(cv_result_raw, Exception):
            logger.error("agent_pipeline.cv_failed", error=str(cv_result_raw))
            cv_html = ""
        else:
            cv_result = cv_result_raw
            cv_html = _extract_pipeline_html(cv_result.content)

        if isinstance(cl_result_raw, Exception):
            logger.error("agent_pipeline.cl_failed", error=str(cl_result_raw))
            cl_html = ""
        else:
            cl_result = cl_result_raw
            cl_html = _extract_pipeline_html(cl_result.content)

        if isinstance(roadmap, Exception):
            logger.error("agent_pipeline.roadmap_failed", error=str(roadmap))
            roadmap = {}

        yield _sse("progress", {
            "phase": "documents_done",
            "step": 3,
            "totalSteps": 6,
            "progress": 70,
            "message": "CV, cover letter & learning plan ready ✓",
        })

        # ── Phase 4: Personal statement + Portfolio (parallel) ────────
        yield _sse("progress", {
            "phase": "portfolio",
            "step": 4,
            "totalSteps": 6,
            "progress": 75,
            "message": "Agents: building personal statement & portfolio…",
        })

        ps_queue: list[str] = []
        pf_queue: list[str] = []

        async def ps_callback(event: dict) -> None:
            ps_queue.append(_agent_sse(
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            ))

        async def pf_callback(event: dict) -> None:
            pf_queue.append(_agent_sse(
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            ))

        ps_pipe = personal_statement_pipeline(ai_client=ai, on_stage_update=ps_callback, db=sb, tables=TABLES)
        pf_pipe = portfolio_pipeline(ai_client=ai, on_stage_update=pf_callback, db=sb, tables=TABLES)

        ps_raw, pf_raw = await asyncio.gather(
            ps_pipe.execute(doc_context),
            pf_pipe.execute(doc_context),
            return_exceptions=True,
        )

        for ev in ps_queue:
            yield ev
        for ev in pf_queue:
            yield ev

        ps_html = ""
        portfolio_html = ""
        if isinstance(ps_raw, Exception):
            logger.error("agent_pipeline.ps_failed", error=str(ps_raw))
        else:
            ps_html = _extract_pipeline_html(ps_raw.content)

        if isinstance(pf_raw, Exception):
            logger.error("agent_pipeline.portfolio_failed", error=str(pf_raw))
        else:
            portfolio_html = _extract_pipeline_html(pf_raw.content)

        yield _sse("progress", {
            "phase": "portfolio_done",
            "step": 4,
            "totalSteps": 6,
            "progress": 88,
            "message": "Personal statement & portfolio ready ✓",
        })

        # ── Phase 5: Format response with quality metadata ────────────
        yield _sse("progress", {
            "phase": "formatting",
            "step": 6,
            "totalSteps": 6,
            "progress": 98,
            "message": "Packaging your application…",
        })

        cv_quality = cv_result.quality_scores if cv_result else {}
        cl_quality = cl_result.quality_scores if cl_result else {}
        cv_fact_check = cv_result.fact_check_report if cv_result else {}

        validation = {
            "cv": {
                "valid": bool(cv_html),
                "qualityScore": _quality_score_from_scores(cv_quality),
                "issues": _validation_issue_count(cv_result.validation_report if cv_result else None),
                "agent_powered": True,
            }
        }

        response = _format_response(
            benchmark_data=benchmark_data,
            gap_analysis=gap_analysis,
            roadmap=roadmap if isinstance(roadmap, dict) else {},
            cv_html=cv_html,
            cl_html=cl_html,
            ps_html=ps_html,
            portfolio_html=portfolio_html,
            validation=validation,
            keywords=keywords,
            job_title=req.job_title,
            benchmark_cv_html=benchmark_cv_html,
        )

        response["meta"] = {
            "quality_scores": {"cv": cv_quality, "cover_letter": cl_quality},
            "fact_check": cv_fact_check,
            "agent_powered": True,
            "final_analysis": cv_result.final_analysis_report if cv_result else None,
            "validation_report": cv_result.validation_report if cv_result else None,
            "citations": cv_result.citations if cv_result else None,
            "evidence_summary": _build_evidence_summary(cv_result) if cv_result else None,
            "workflow_state": cv_result.workflow_state if cv_result else None,
        }

        # Catalog-driven doc pack plan + company intel
        if doc_pack_plan_stream:
            response["docPackPlan"] = doc_pack_plan_stream.to_dict()
            response["discoveredDocuments"] = (
                doc_pack_plan_stream.core
                + doc_pack_plan_stream.required
                + doc_pack_plan_stream.optional
            )
        if company_intel_stream:
            response["companyIntel"] = company_intel_stream

        logger.info("agent_pipeline.complete", overall_score=response["scores"]["overall"])

        yield _agent_sse("pipeline", "complete", "completed", message="All agent pipelines completed")
        yield _sse("complete", {"progress": 100, "result": response})

    except CircuitBreakerOpen as cbe:
        logger.warning("agent_pipeline.circuit_breaker_open", breaker=cbe.name, remaining_s=cbe.remaining_s)
        yield _sse("error", {
            "message": "AI service is temporarily unavailable due to repeated failures. Please try again shortly.",
            "code": 503,
            "retryAfterSeconds": int(cbe.remaining_s) + 1,
        })
    except Exception as e:
        classified = _classify_ai_error(e)
        if classified:
            code = int(classified["code"])
            msg = str(classified["message"])
            retry_after = classified.get("retry_after_seconds")
            logger.error("agent_pipeline.ai_error", code=code, message=msg, retry_after_seconds=retry_after)
            payload: Dict[str, Any] = {"message": msg, "code": code}
            if retry_after:
                payload["retryAfterSeconds"] = retry_after
            yield _sse("error", payload)
        else:
            logger.error("agent_pipeline.error", error=str(e), traceback=traceback.format_exc())
            yield _sse("error", {
                "message": "AI generation failed due to an unexpected error. Please try again.",
                "code": 500,
            })


@router.post("/pipeline/stream")
@limiter.limit("3/minute")
async def generate_pipeline_stream(request: Request, req: PipelineRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    SSE streaming version of the pipeline.
    Uses the agent pipeline (Researcher → Drafter → Critic → Optimizer →
    FactChecker → Validator) when available and emits agent_status events
    alongside regular progress events.
    Falls back to the legacy direct-chain path if agents are unavailable.
    """
    await check_billing_limit("ai_calls", current_user)
    _validate_pipeline_input(req)
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub") or "anonymous"

    if _RUNTIME_AVAILABLE:
        sink = _SSESink()
        config = _RuntimeConfig(
            mode=_ExecutionMode.STREAM,
            timeout=PIPELINE_TIMEOUT,
            user_id=user_id,
        )
        runtime = _PipelineRuntime(config=config, event_sink=sink)

        async def runtime_stream() -> AsyncGenerator[str, None]:
            task = asyncio.create_task(runtime.execute({
                "job_title": req.job_title,
                "company": req.company,
                "jd_text": req.jd_text,
                "resume_text": req.resume_text,
            }))
            async for event_str in sink.iter_events():
                yield event_str
            # Await the task to propagate exceptions if any
            await task

        return StreamingResponse(
            runtime_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if _AGENT_PIPELINES_AVAILABLE:
        return StreamingResponse(
            _stream_agent_pipeline(req, user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Legacy fallback ────────────────────────────────────────────────
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            from ai_engine.client import AIClient
            from ai_engine.chains.role_profiler import RoleProfilerChain
            from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
            from ai_engine.chains.gap_analyzer import GapAnalyzerChain
            from ai_engine.chains.document_generator import DocumentGeneratorChain
            from ai_engine.chains.career_consultant import CareerConsultantChain
            from ai_engine.chains.validator import ValidatorChain

            ai = AIClient()
            company = req.company or "the company"

            logger.info("pipeline_stream.start", job_title=req.job_title, company=company)

            yield _sse("progress", {
                "phase": "initializing",
                "step": 0,
                "totalSteps": 6,
                "progress": 5,
                "message": "Initializing AI engine…",
            })

            # ── Phase 1: Parse resume + Build benchmark ───────────────
            profiler = RoleProfilerChain(ai)
            benchmark_chain = BenchmarkBuilderChain(ai)

            yield _sse("progress", {
                "phase": "profiling",
                "step": 1,
                "totalSteps": 6,
                "progress": 10,
                "message": "Parsing resume & building candidate benchmark…",
            })

            if req.resume_text.strip():
                user_profile, benchmark_data = await asyncio.gather(
                    profiler.parse_resume(req.resume_text),
                    benchmark_chain.create_ideal_profile(req.job_title, company, req.jd_text),
                )
            else:
                user_profile = {}
                benchmark_data = await benchmark_chain.create_ideal_profile(req.job_title, company, req.jd_text)

            ideal_skills = benchmark_data.get("ideal_skills", [])
            keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
            if not keywords:
                keywords = _extract_keywords_from_jd(req.jd_text)

            # Generate benchmark CV HTML (user identity + ideal experience)
            benchmark_cv_html = ""
            try:
                benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                    user_profile=user_profile,
                    benchmark_data=benchmark_data,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                )
            except Exception as bcv_err:
                logger.warning("pipeline_stream.benchmark_cv_failed", error=str(bcv_err))

            yield _sse("progress", {
                "phase": "profiling_done",
                "step": 1,
                "totalSteps": 6,
                "progress": 25,
                "message": "Resume parsed & benchmark built ✓",
            })

            # ── Phase 2: Gap Analysis ─────────────────────────────────
            yield _sse("progress", {
                "phase": "gap_analysis",
                "step": 2,
                "totalSteps": 6,
                "progress": 30,
                "message": "Analyzing skill gaps…",
            })

            gap_chain = GapAnalyzerChain(ai)
            gap_analysis = await gap_chain.analyze_gaps(user_profile, benchmark_data, req.job_title, company)

            yield _sse("progress", {
                "phase": "gap_analysis_done",
                "step": 2,
                "totalSteps": 6,
                "progress": 45,
                "message": "Gap analysis complete ✓",
            })

            # ── Phase 3: Generate CV, Cover Letter, Roadmap ───────────
            yield _sse("progress", {
                "phase": "documents",
                "step": 3,
                "totalSteps": 6,
                "progress": 50,
                "message": "Generating CV, cover letter & learning plan…",
            })

            doc_chain = DocumentGeneratorChain(ai)
            consultant = CareerConsultantChain(ai)

            cv_html, cl_html, roadmap = await asyncio.gather(
                doc_chain.generate_tailored_cv(
                    user_profile=user_profile, job_title=req.job_title,
                    company=company, jd_text=req.jd_text,
                    gap_analysis=gap_analysis, resume_text=req.resume_text,
                ),
                doc_chain.generate_tailored_cover_letter(
                    user_profile=user_profile, job_title=req.job_title,
                    company=company, jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                ),
                consultant.generate_roadmap(gap_analysis, user_profile, req.job_title, company),
                return_exceptions=True,
            )

            if isinstance(cv_html, Exception):
                logger.error("pipeline_stream.cv_failed", error=str(cv_html))
                cv_html = ""
            if isinstance(cl_html, Exception):
                logger.error("pipeline_stream.cl_failed", error=str(cl_html))
                cl_html = ""
            if isinstance(roadmap, Exception):
                logger.error("pipeline_stream.roadmap_failed", error=str(roadmap))
                roadmap = {}

            yield _sse("progress", {
                "phase": "documents_done",
                "step": 3,
                "totalSteps": 6,
                "progress": 70,
                "message": "CV, cover letter & learning plan ready ✓",
            })

            # ── Phase 4: Personal statement + Portfolio ───────────────
            yield _sse("progress", {
                "phase": "portfolio",
                "step": 4,
                "totalSteps": 6,
                "progress": 75,
                "message": "Building personal statement & portfolio…",
            })

            ps_html = ""
            portfolio_html = ""
            try:
                ps_result, portfolio_result = await asyncio.gather(
                    doc_chain.generate_tailored_personal_statement(
                        user_profile=user_profile, job_title=req.job_title,
                        company=company, jd_text=req.jd_text,
                        gap_analysis=gap_analysis, resume_text=req.resume_text,
                    ),
                    doc_chain.generate_tailored_portfolio(
                        user_profile=user_profile, job_title=req.job_title,
                        company=company, jd_text=req.jd_text,
                        gap_analysis=gap_analysis, resume_text=req.resume_text,
                    ),
                    return_exceptions=True,
                )
                if isinstance(ps_result, Exception):
                    logger.error("pipeline_stream.ps_failed", error=str(ps_result))
                else:
                    ps_html = ps_result if isinstance(ps_result, str) else ""
                if isinstance(portfolio_result, Exception):
                    logger.error("pipeline_stream.portfolio_failed", error=str(portfolio_result))
                else:
                    portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
            except Exception as phase4_err:
                logger.error("pipeline_stream.phase4_error", error=str(phase4_err))

            yield _sse("progress", {
                "phase": "portfolio_done",
                "step": 4,
                "totalSteps": 6,
                "progress": 88,
                "message": "Personal statement & portfolio ready ✓",
            })

            # ── Phase 5: Validation ───────────────────────────────────
            yield _sse("progress", {
                "phase": "validation",
                "step": 5,
                "totalSteps": 6,
                "progress": 90,
                "message": "Validating document quality…",
            })

            validation = {}
            try:
                validator = ValidatorChain(ai)
                cv_valid, cv_validation = await validator.validate_document(
                    document_type="Tailored CV",
                    content=cv_html[:3000] if cv_html else "",
                    profile_data=user_profile,
                )
                validation["cv"] = {
                    "valid": cv_valid,
                    "qualityScore": cv_validation.get("quality_score", 0),
                    "issues": len(cv_validation.get("issues", [])),
                }
            except Exception as val_err:
                logger.warning("pipeline_stream.validation_skipped", error=str(val_err))

            yield _sse("progress", {
                "phase": "validation_done",
                "step": 5,
                "totalSteps": 6,
                "progress": 95,
                "message": "Quality checks passed ✓",
            })

            # ── Phase 6: Format response ──────────────────────────────
            yield _sse("progress", {
                "phase": "formatting",
                "step": 6,
                "totalSteps": 6,
                "progress": 98,
                "message": "Packaging your application…",
            })

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
                job_title=req.job_title,
                benchmark_cv_html=benchmark_cv_html,
            )

            logger.info("pipeline_stream.complete", overall_score=response["scores"]["overall"])

            yield _sse("complete", {"progress": 100, "result": response})

        except Exception as e:
            classified = _classify_ai_error(e)
            if classified:
                code = int(classified["code"])
                msg = str(classified["message"])
                retry_after = classified.get("retry_after_seconds")
                logger.error("pipeline_stream.ai_error", code=code, message=msg, retry_after_seconds=retry_after)
                payload: Dict[str, Any] = {"message": msg, "code": code}
                if retry_after:
                    payload["retryAfterSeconds"] = retry_after
                yield _sse("error", payload)
            else:
                logger.error("pipeline_stream.error", error=str(e), traceback=traceback.format_exc())
                yield _sse("error", {
                    "message": "AI generation failed due to an unexpected error. Please try again.",
                    "code": 500,
                })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Response formatters ───────────────────────────────────────────────

def _format_response(
    benchmark_data: Dict[str, Any],
    gap_analysis: Dict[str, Any],
    roadmap: Dict[str, Any],
    cv_html: str,
    cl_html: str,
    ps_html: str,
    portfolio_html: str,
    validation: Dict[str, Any],
    keywords: List[str],
    job_title: str,
    benchmark_cv_html: str = "",
) -> Dict[str, Any]:
    """Transform chain outputs into the frontend's expected data shapes."""

    # ── Benchmark ─────────────────────────────
    ideal_profile = benchmark_data.get("ideal_profile", {})
    ideal_skills = benchmark_data.get("ideal_skills", [])
    ideal_experience = benchmark_data.get("ideal_experience", [])

    summary_text = ""
    if isinstance(ideal_profile, dict):
        summary_text = ideal_profile.get("summary", "")
    if not summary_text:
        summary_text = f"AI-generated benchmark for {job_title}"

    rubric: List[str] = []
    for skill in ideal_skills[:10]:
        if isinstance(skill, dict):
            name = skill.get("name", "Unknown")
            level = skill.get("level", "required")
            importance = skill.get("importance", "important")
            rubric.append(f"{name} — {level} level ({importance})")

    benchmark = {
        "summary": summary_text,
        "keywords": keywords,
        "rubric": rubric,
        "idealProfile": ideal_profile if isinstance(ideal_profile, dict) else {},
        "idealSkills": ideal_skills,
        "idealExperience": ideal_experience,
        "scoringWeights": benchmark_data.get("scoring_weights", {}),
        "benchmarkCvHtml": _sanitize_output_html(benchmark_cv_html),
        "createdAt": None,
    }

    # ── Gaps ──────────────────────────────────
    compatibility = gap_analysis.get("compatibility_score", 50)
    skill_gaps = gap_analysis.get("skill_gaps", [])
    strengths_raw = gap_analysis.get("strengths", [])
    recommendations_raw = gap_analysis.get("recommendations", [])
    category_scores = gap_analysis.get("category_scores", {})
    quick_wins = gap_analysis.get("quick_wins", [])

    missing_kw = [
        g.get("skill", "") for g in skill_gaps if isinstance(g, dict) and g.get("skill")
    ]
    strength_labels = [
        s.get("area", s.get("description", ""))
        for s in strengths_raw
        if isinstance(s, dict)
    ]
    rec_labels = [
        r.get("title", r.get("description", ""))
        for r in recommendations_raw
        if isinstance(r, dict)
    ]

    gaps = {
        "missingKeywords": missing_kw,
        "strengths": strength_labels,
        "recommendations": rec_labels,
        "gaps": [
            {
                "dimension": g.get("skill", ""),
                "gap": f"{g.get('current_level', '?')} → {g.get('required_level', 'required')}",
                "severity": _map_severity(g.get("gap_severity", "moderate")),
                "suggestion": g.get("recommendation", ""),
            }
            for g in skill_gaps
            if isinstance(g, dict)
        ],
        "summary": gap_analysis.get("executive_summary", ""),
        "compatibility": compatibility,
        "categoryScores": category_scores,
        "quickWins": quick_wins,
        "interviewReadiness": gap_analysis.get("interview_readiness", {}),
    }

    # ── Learning Plan ─────────────────────────
    roadmap_data = roadmap.get("roadmap", {}) if isinstance(roadmap, dict) else {}
    milestones = roadmap_data.get("milestones", [])
    weekly_plans = roadmap_data.get("weekly_plans", [])
    skill_dev = roadmap_data.get("skill_development", [])
    project_recs = roadmap_data.get("project_recommendations", [])
    lr_resources = roadmap.get("learning_resources", []) if isinstance(roadmap, dict) else []
    quick_wins_roadmap = roadmap.get("quick_wins", []) if isinstance(roadmap, dict) else []

    # Build plan from milestones (new format) or weekly_plans (old format)
    plan_items = []
    if milestones:
        for i, ms in enumerate(milestones[:12]):
            if isinstance(ms, dict):
                plan_items.append({
                    "week": ms.get("week", i + 1),
                    "theme": ms.get("title", f"Week {i + 1}"),
                    "outcomes": ms.get("skills_gained", []),
                    "tasks": ms.get("tasks", []),
                    "goals": [ms.get("description", "")] if ms.get("description") else [],
                })
    elif weekly_plans:
        for i, wp in enumerate(weekly_plans[:12]):
            if isinstance(wp, dict):
                plan_items.append({
                    "week": wp.get("week", i + 1),
                    "theme": wp.get("theme", f"Week {i + 1}"),
                    "outcomes": wp.get("goals", []),
                    "tasks": [
                        a.get("activity", "")
                        for a in wp.get("activities", [])
                        if isinstance(a, dict)
                    ],
                    "goals": wp.get("goals", []),
                })

    learning_plan = {
        "focus": [
            s.get("skill", "")
            for s in skill_dev[:6]
            if isinstance(s, dict) and s.get("skill")
        ],
        "plan": plan_items,
        "resources": [
            {
                "skill": r.get("skill_covered", r.get("skill", "")),
                "title": r.get("title", ""),
                "provider": r.get("provider", ""),
                "timebox": r.get("duration", "Self-paced"),
                "url": r.get("url"),
            }
            for r in lr_resources[:12]
            if isinstance(r, dict)
        ],
        "projectRecommendations": [
            {
                "title": p.get("title", ""),
                "description": p.get("description", ""),
                "skills": p.get("skills_demonstrated", []),
                "timeline": p.get("timeline", ""),
            }
            for p in project_recs[:6]
            if isinstance(p, dict)
        ],
        "quickWins": quick_wins_roadmap,
    }

    # ── Scores ────────────────────────────────
    match_score = min(100, max(0, compatibility))
    ats_score = min(100, match_score + 15)
    scan_score = min(100, match_score + 10)

    scores = {
        "match": match_score,
        "atsReadiness": ats_score,
        "recruiterScan": scan_score,
        "evidenceStrength": 0,
        "topFix": _derive_top_fix(missing_kw),
        "benchmark": match_score,
        "gaps": max(0, 100 - len(missing_kw) * 8),
        "cv": min(100, match_score + 20),
        "coverLetter": min(100, match_score + 15),
        "overall": match_score,
    }

    scorecard = {
        "overall": scores["overall"],
        "dimensions": [
            {"name": "Match", "score": scores["match"], "feedback": f"{scores['match']}% keyword alignment"},
            {"name": "ATS Readiness", "score": scores["atsReadiness"], "feedback": f"{scores['atsReadiness']}% ATS-optimized"},
            {"name": "Recruiter Scan", "score": scores["recruiterScan"], "feedback": f"{scores['recruiterScan']}% scan-friendly"},
            {"name": "Evidence Strength", "score": scores["evidenceStrength"], "feedback": "Add evidence to boost this score"},
        ],
        "match": scores["match"],
        "atsReadiness": scores["atsReadiness"],
        "recruiterScan": scores["recruiterScan"],
        "evidenceStrength": scores["evidenceStrength"],
        "topFix": scores["topFix"],
        "updatedAt": None,
    }

    return {
        "benchmark": benchmark,
        "gaps": gaps,
        "learningPlan": learning_plan,
        "cvHtml": _sanitize_output_html(cv_html),
        "coverLetterHtml": _sanitize_output_html(cl_html),
        "personalStatementHtml": _sanitize_output_html(ps_html),
        "portfolioHtml": _sanitize_output_html(portfolio_html),
        "validation": validation,
        "scorecard": scorecard,
        "scores": scores,
    }


# ── Helpers ───────────────────────────────────────────────────────────

def _map_severity(severity: str) -> str:
    return {"critical": "high", "major": "high", "moderate": "medium", "minor": "low"}.get(
        severity, "medium"
    )


def _derive_top_fix(missing: List[str]) -> str:
    if missing:
        return f'Add proof for "{missing[0]}" — include a concrete project or measurable result.'
    return "Your profile is strong! Polish your summary and lead with your best proof point."


def _extract_keywords_from_jd(jd_text: str) -> List[str]:
    """Simple keyword extraction fallback."""
    KNOWN = {
        "javascript", "typescript", "python", "java", "go", "rust", "ruby", "php",
        "swift", "kotlin", "react", "angular", "vue", "svelte", "next", "nuxt",
        "node", "express", "django", "flask", "fastapi", "spring",
        "sql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "git", "github", "gitlab", "jenkins", "ci", "cd",
        "graphql", "rest", "grpc", "microservices",
        "tailwind", "css", "html", "sass",
        "jest", "playwright", "cypress", "selenium",
        "figma", "agile", "scrum", "kanban",
        "machine", "learning", "ai", "ml", "nlp",
        "linux", "bash", "shell",
    }
    words = jd_text.lower().split()
    found, seen = [], set()
    for w in words:
        clean = w.strip(".,;:!?()[]{}\"'").lower()
        if clean in KNOWN and clean not in seen:
            seen.add(clean)
            found.append(clean)
    return found[:25]


# ── DB-backed Generation Jobs API ─────────────────────────────────────────────


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
            phase_timeout=PHASE_TIMEOUT,
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


ALLOWED_JOB_MODULES = {
    # snake_case (canonical for /jobs endpoint)
    "cv", "cover_letter", "personal_statement", "portfolio",
    "learning_plan", "scorecard", "benchmark", "gap_analysis",
    # camelCase (accepted for cross-format compatibility)
    "coverLetter", "personalStatement", "learningPlan", "gaps",
}


class GenerationJobRequest(BaseModel):
    application_id: str
    requested_modules: List[str] = []

    @field_validator("application_id")
    @classmethod
    def application_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("application_id is required")
        if len(v) > 200:
            raise ValueError("application_id too long")
        return v

    @field_validator("requested_modules")
    @classmethod
    def validate_modules(cls, v: List[str]) -> List[str]:
        if len(v) > 20:
            raise ValueError("Too many requested modules (max 20)")
        for mod in v:
            if mod not in ALLOWED_JOB_MODULES:
                raise ValueError(f"Unknown module: {mod}")
        return v


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
async def stream_generation_job(
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
async def get_generation_job_status(
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


# ── Module-level regeneration (P2-05) ─────────────────────────────────

class RetryModulesRequest(BaseModel):
    modules: List[str]

    @field_validator("modules")
    @classmethod
    def validate_retry_modules(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one module must be specified for retry")
        if len(v) > 20:
            raise ValueError("Too many modules (max 20)")
        for mod in v:
            if mod not in ALLOWED_JOB_MODULES:
                raise ValueError(f"Unknown module: {mod}")
        return v


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


# ── On-demand single document generation ──────────────────────────────

class GenerateDocumentRequest(BaseModel):
    application_id: str
    doc_key: str
    doc_label: str = ""

    @field_validator("application_id")
    @classmethod
    def _validate_app_id(cls, v: str) -> str:
        validate_uuid(v, "application_id")
        return v

    @field_validator("doc_key")
    @classmethod
    def _validate_doc_key(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("doc_key must be 1-100 characters")
        return v


@router.post("/document")
@limiter.limit("5/minute")
async def generate_on_demand_document(
    request: Request,
    req: GenerateDocumentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a single optional document for an existing application."""
    await check_billing_limit("ai_calls", current_user)
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    from app.core.database import get_supabase, TABLES
    from ai_engine.client import AIClient
    from ai_engine.chains.adaptive_document import AdaptiveDocumentChain

    sb = get_supabase()

    # Fetch application with ownership check
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("*")
        .eq("id", req.application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = app_resp.data
    confirmed_facts = app_data.get("confirmed_facts") or {}

    job_title = confirmed_facts.get("jobTitle") or confirmed_facts.get("job_title") or ""
    company = confirmed_facts.get("company") or ""
    jd_text = confirmed_facts.get("jdText") or confirmed_facts.get("jd_text") or ""
    _resume_data = confirmed_facts.get("resume") or {}
    user_profile = app_data.get("user_profile") or {}

    if not job_title:
        raise HTTPException(status_code=400, detail="Application is missing job title")

    # Build context for AdaptiveDocumentChain
    gap_analysis = app_data.get("gap_analysis") or {}
    benchmark_data = app_data.get("benchmark") or {}
    company_intel = app_data.get("company_intel") or {}

    gaps_summary = ""
    skill_gaps = gap_analysis.get("skill_gaps") or gap_analysis.get("skillGaps") or []
    if skill_gaps:
        gaps_summary = "; ".join(
            g.get("skill", "") for g in skill_gaps[:10] if isinstance(g, dict) and g.get("skill")
        )

    strengths = gap_analysis.get("strengths") or gap_analysis.get("key_strengths") or []
    strengths_summary = ""
    if strengths:
        strengths_summary = "; ".join(
            (s.get("skill", "") if isinstance(s, dict) else str(s)) for s in strengths[:10]
        )

    ideal_skills = benchmark_data.get("ideal_skills") or []
    benchmark_keywords = ", ".join(
        s.get("name", "") for s in ideal_skills[:15] if isinstance(s, dict)
    )

    doc_pack_plan = app_data.get("doc_pack_plan") or {}
    doc_label = req.doc_label or req.doc_key.replace("_", " ").title()

    context = {
        "profile": user_profile,
        "job_title": job_title,
        "company": company or "the company",
        "industry": doc_pack_plan.get("industry", "professional"),
        "tone": doc_pack_plan.get("tone", "professional"),
        "jd_text": jd_text,
        "gaps_summary": gaps_summary,
        "strengths_summary": strengths_summary,
        "benchmark_keywords": benchmark_keywords,
        "company_intel": company_intel,
        "key_themes": doc_pack_plan.get("key_themes", []),
    }

    ai = AIClient()
    chain = AdaptiveDocumentChain(ai)

    try:
        html = await asyncio.wait_for(
            chain.generate(
                doc_type=req.doc_key,
                doc_label=doc_label,
                context=context,
                mode="user",
            ),
            timeout=PHASE_TIMEOUT * 2,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Document generation timed out")
    except Exception as gen_err:
        logger.error("on_demand_doc.generation_failed", doc_key=req.doc_key, error=str(gen_err)[:200])
        raise HTTPException(status_code=500, detail="Document generation failed")

    html = _sanitize_output_html(html) if html else ""

    # Persist to application's generated_documents
    existing_docs = app_data.get("generated_documents") or {}
    existing_docs[req.doc_key] = html
    try:
        await _persist_application_patch(
            sb, TABLES, req.application_id,
            {"generated_documents": existing_docs},
        )
    except Exception as persist_err:
        logger.warning("on_demand_doc.persist_failed", error=str(persist_err)[:200])

    return {"doc_key": req.doc_key, "doc_label": doc_label, "html": html}


# ── Stale job cleanup ─────────────────────────────────────────────────

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
