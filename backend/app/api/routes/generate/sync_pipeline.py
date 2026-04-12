"""Synchronous pipeline endpoint (POST /pipeline)."""
import asyncio
import traceback
import structlog
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user, check_billing_limit
from app.core.security import limiter

from .schemas import PipelineRequest
from .helpers import (
    MAX_JD_SIZE,
    MAX_RESUME_SIZE,
    PIPELINE_TIMEOUT,
    _RUNTIME_AVAILABLE,
    _classify_ai_error,
    _extract_keywords_from_jd,
    _format_response,
    _sanitize_output_html,
    _validate_pipeline_input,
    logger,
)

try:
    from .helpers import _PipelineRuntime, _RuntimeConfig, _ExecutionMode, _CollectorSink
except ImportError:
    pass

from .helpers import CircuitBreakerOpen

router = APIRouter()

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
        discovery = await discovery_chain.discover(req.jd_text, req.job_title, company)
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
        company_intel = await intel_chain.gather_intel(
            company=company,
            job_title=req.job_title,
            jd_text=req.jd_text,
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
        user_profile, benchmark_data = await asyncio.gather(
            profiler.parse_resume(req.resume_text),
            benchmark_chain.create_ideal_profile(
                req.job_title, company, req.jd_text
            ),
        )
    else:
        user_profile = {}
        benchmark_data = await benchmark_chain.create_ideal_profile(
            req.job_title, company, req.jd_text
        )

    logger.info("pipeline.phase1_done", has_profile=bool(user_profile))

    # Generate benchmark documents for ALL required types (100% match)
    benchmark_cv_html = ""
    benchmark_documents = {}
    try:
        benchmark_result = await benchmark_chain.generate_perfect_application(
            jd_text=req.jd_text,
            job_title=req.job_title,
            company=company,
            user_profile=user_profile,
            required_documents=required_docs,
            discovery_context=discovery,
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
    gap_analysis = await gap_chain.analyze_gaps(
        user_profile, benchmark_data, req.job_title, company
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
            cv_valid, cv_validation = await validator.validate_document(
                document_type="Tailored CV",
                content=cv_html[:3000],
                profile_data=user_profile,
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

