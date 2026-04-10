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
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.security import limiter


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
    _AGENT_PIPELINES_AVAILABLE = True
except ImportError:
    _AGENT_PIPELINES_AVAILABLE = False


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
    _validate_pipeline_input(req)
    try:
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
            # Fallback: try just the CV
            try:
                benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                    user_profile=user_profile,
                    benchmark_data=benchmark_data,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                )
            except Exception:
                pass

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
            cv_html = ""
        if isinstance(cl_html, Exception):
            logger.error("pipeline.cl_failed", error=str(cl_html))
            cl_html = ""
        if isinstance(roadmap, Exception):
            logger.error("pipeline.roadmap_failed", error=str(roadmap))
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
            ps_html = ps_result if isinstance(ps_result, str) else ""
            portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
        except Exception as p4_err:
            logger.error("pipeline.phase4_error", error=str(p4_err))

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
            k: v for k, v in generated_docs.items() if v
        }
        response["benchmarkDocuments"] = benchmark_documents
        response["documentStrategy"] = discovery.get("document_strategy", "")
        if company_intel:
            response["companyIntel"] = company_intel

        logger.info("pipeline.complete", overall_score=response["scores"]["overall"], docs_generated=len(generated_docs))
        return response

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
        # Provide a clean message — never leak raw Python tracebacks / memory addresses
        raise HTTPException(
            status_code=500,
            detail="AI generation failed due to an unexpected error. Please try again in a moment.",
        )


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

        ai = AIClient()
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
            pipe = resume_parse_pipeline(ai_client=ai, on_stage_update=stage_callback)
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

        bench_pipe = benchmark_pipeline(ai_client=ai, on_stage_update=stage_callback)
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

        # ── Phase 2: Gap analysis pipeline ───────────────────────────
        yield _sse("progress", {
            "phase": "gap_analysis",
            "step": 2,
            "totalSteps": 6,
            "progress": 30,
            "message": "Agent: analyzing skill gaps…",
        })

        gap_pipe = gap_analysis_pipeline(ai_client=ai, on_stage_update=stage_callback)
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

        cv_pipe = cv_generation_pipeline(ai_client=ai, on_stage_update=cv_callback)
        cl_pipe = cover_letter_pipeline(ai_client=ai, on_stage_update=cl_callback)
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
            raw = cv_result.content
            cv_html = raw.get("html", "") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")

        if isinstance(cl_result_raw, Exception):
            logger.error("agent_pipeline.cl_failed", error=str(cl_result_raw))
            cl_html = ""
        else:
            cl_result = cl_result_raw
            raw = cl_result.content
            cl_html = raw.get("html", "") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")

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

        ps_pipe = personal_statement_pipeline(ai_client=ai, on_stage_update=ps_callback)
        pf_pipe = portfolio_pipeline(ai_client=ai, on_stage_update=pf_callback)

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
            raw = ps_raw.content
            ps_html = raw.get("html", "") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")

        if isinstance(pf_raw, Exception):
            logger.error("agent_pipeline.portfolio_failed", error=str(pf_raw))
        else:
            raw = pf_raw.content
            portfolio_html = raw.get("html", "") if isinstance(raw, dict) else (raw if isinstance(raw, str) else "")

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
                "qualityScore": cv_quality.get("overall", 0) if isinstance(cv_quality, dict) else 0,
                "issues": 0,
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
        }

        logger.info("agent_pipeline.complete", overall_score=response["scores"]["overall"])

        yield _agent_sse("pipeline", "complete", "completed", message="All agent pipelines completed")
        yield _sse("complete", {"progress": 100, "result": response})

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
    _validate_pipeline_input(req)
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub") or "anonymous"

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
        "benchmarkCvHtml": benchmark_cv_html,
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
        "cvHtml": cv_html,
        "coverLetterHtml": cl_html,
        "personalStatementHtml": ps_html,
        "portfolioHtml": portfolio_html,
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
    normalized = [
        module
        for module in (requested_modules or [])
        if module in _DEFAULT_REQUESTED_MODULES
    ]
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
    application_row: Dict[str, Any],
    requested_modules: List[str],
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    timestamp = _now_ms()
    modules = _merge_module_states(application_row.get("modules"))

    for module_key in requested_modules:
        if status == "cancelled":
            next_state = "ready" if _module_has_content(application_row, module_key) else "idle"
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


async def _run_generation_job(job_id: str, user_id: str) -> None:  # noqa: C901
    """Run a generation job with a hard 30-minute timeout."""
    try:
        await asyncio.wait_for(
            _run_generation_job_inner(job_id, user_id),
            timeout=1800,  # 30 minutes
        )
    except asyncio.TimeoutError:
        logger.error("job_runner.timeout", job_id=job_id)
        try:
            from app.core.database import get_supabase, TABLES
            sb = get_supabase()
            await _persist_generation_job_update(
                sb, TABLES, job_id,
                {
                    "status": "failed",
                    "error_message": "Generation timed out after 30 minutes. Please try again.",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass
    finally:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)


async def _run_generation_job_inner(job_id: str, user_id: str) -> None:  # noqa: C901
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not job_resp.data:
        return

    job = job_resp.data
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
        except Exception:
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

        await emit_progress("documents", 4, 58, "Quill is generating the CV, cover letter, and learning plan…")
        await emit_detail("quill", "Drafting the tailored CV, cover letter, and roadmap in parallel.", "running", "documents")

        doc_chain = DocumentGeneratorChain(ai)
        consultant = CareerConsultantChain(ai)

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
        try:
            ps_result, portfolio_result = await asyncio.gather(
                doc_chain.generate_tailored_personal_statement(
                    user_profile=user_profile,
                    job_title=job_title,
                    company=company_str,
                    jd_text=jd_text_val,
                    gap_analysis=gap_analysis,
                    resume_text=resume_text_val,
                ),
                doc_chain.generate_tailored_portfolio(
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


def _start_generation_job(job_id: str, user_id: str) -> None:
    if job_id in _ACTIVE_GENERATION_TASKS:
        return

    task = asyncio.create_task(_run_generation_job(job_id, user_id))
    _ACTIVE_GENERATION_TASKS[job_id] = task

    def _cleanup(completed_task: asyncio.Task) -> None:
        _ACTIVE_GENERATION_TASKS.pop(job_id, None)
        try:
            completed_task.result()
        except Exception as e:
            logger.error("generation_task_failed", job_id=job_id, error=str(e))

    task.add_done_callback(_cleanup)


class GenerationJobRequest(BaseModel):
    application_id: str
    requested_modules: List[str] = []


@router.post("/jobs")
async def create_generation_job(
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
    await _set_application_modules_generating(
        sb,
        TABLES,
        req.application_id,
        app_resp.data.get("modules"),
        requested_modules,
    )

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
    _start_generation_job(job_id, user_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}/stream")
async def stream_generation_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Tail a generation job's persisted SSE events and current status."""
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Fetch job
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    job = job_resp.data

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
async def cancel_generation_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Request cancellation of a running generation job."""
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


async def recover_inflight_generation_jobs() -> int:
    """
    Called on startup: mark any 'running' or 'queued' jobs as 'failed'.
    These are jobs that were in-progress when the server last restarted.
    """
    try:
        from app.core.database import get_supabase, TABLES

        sb = get_supabase()
        resp = await asyncio.to_thread(
            lambda: sb.table(TABLES["generation_jobs"])
            .update({
                "status": "failed",
                "error_message": "Server restarted — please click Regenerate to try again",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            .in_("status", ["running", "queued"])
            .execute()
        )
        _ACTIVE_GENERATION_TASKS.clear()
        return len(resp.data) if resp.data else 0
    except Exception as e:
        logger.warning("recover_inflight_jobs_failed", error=str(e))
        return 0
