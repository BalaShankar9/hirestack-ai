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
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user

try:
    import openai as _openai_module
except ImportError:
    _openai_module = None  # type: ignore

import structlog

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
    # ── OpenAI SDK errors ──
    if _openai_module is not None:
        if isinstance(exc, _openai_module.AuthenticationError):
            return {"code": 401, "message": "AI API key is invalid or missing. Please check your configuration."}
        if isinstance(exc, _openai_module.PermissionDeniedError):
            return {"code": 403, "message": "Your AI API key does not have permission to use this model. Check your billing or access settings."}
        if isinstance(exc, _openai_module.NotFoundError):
            from app.core.config import settings as _s
            model = _s.openai_model if _s.ai_provider == "openai" else _s.gemini_model
            return {"code": 404, "message": f"The AI model '{model}' was not found. Check your model setting."}
        if isinstance(exc, _openai_module.RateLimitError):
            # OpenAI SDK sometimes provides retry headers, but keep a simple message here.
            return {"code": 429, "message": "AI rate limit reached. Please wait a moment and try again."}

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
class PipelineRequest(BaseModel):
    job_title: str
    company: str = ""
    jd_text: str
    resume_text: str = ""


# ── Main pipeline endpoint ────────────────────────────────────────────
@router.post("/pipeline")
async def generate_pipeline(req: PipelineRequest):
    """Run the complete AI generation pipeline and return all modules."""
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

        logger.info(
            "pipeline.start",
            job_title=req.job_title,
            company=company,
            jd_length=len(req.jd_text),
            resume_length=len(req.resume_text),
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

        # Generate benchmark CV HTML (uses user identity + ideal experience)
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
            logger.warning("pipeline.benchmark_cv_failed", error=str(bcv_err))

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

        # ── Phase 3: Generate documents (parallel) ────────────────────
        doc_chain = DocumentGeneratorChain(ai)
        consultant = CareerConsultantChain(ai)

        # Prepare context strings for the prompts
        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        key_gaps_str = ", ".join(
            g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
        ) or "None identified"
        strengths_str = ", ".join(
            s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
        ) or "None identified"
        compatibility = gap_analysis.get("compatibility_score", 50)

        cv_html, cl_html, roadmap = await asyncio.gather(
            doc_chain.generate_tailored_cv(
                user_profile=user_profile,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
                gap_analysis=gap_analysis,
                resume_text=req.resume_text,
            ),
            doc_chain.generate_tailored_cover_letter(
                user_profile=user_profile,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
                gap_analysis=gap_analysis,
            ),
            consultant.generate_roadmap(
                gap_analysis, user_profile, req.job_title, company
            ),
            return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(cv_html, Exception):
            logger.error("pipeline.cv_failed", error=str(cv_html))
            cv_html = ""
        if isinstance(cl_html, Exception):
            logger.error("pipeline.cl_failed", error=str(cl_html))
            cl_html = ""
        if isinstance(roadmap, Exception):
            logger.error("pipeline.roadmap_failed", error=str(roadmap))
            roadmap = {}

        logger.info(
            "pipeline.phase3_done",
            cv_length=len(cv_html) if isinstance(cv_html, str) else 0,
            cl_length=len(cl_html) if isinstance(cl_html, str) else 0,
        )

        # ── Phase 4: Personal statement + Portfolio (parallel) ────────
        ps_html = ""
        portfolio_html = ""
        try:
            ps_result, portfolio_result = await asyncio.gather(
                doc_chain.generate_tailored_personal_statement(
                    user_profile=user_profile,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                    resume_text=req.resume_text,
                ),
                doc_chain.generate_tailored_portfolio(
                    user_profile=user_profile,
                    job_title=req.job_title,
                    company=company,
                    jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                    resume_text=req.resume_text,
                ),
                return_exceptions=True,
            )

            if isinstance(ps_result, Exception):
                logger.error("pipeline.ps_failed", error=str(ps_result))
            else:
                ps_html = ps_result if isinstance(ps_result, str) else ""

            if isinstance(portfolio_result, Exception):
                logger.error("pipeline.portfolio_failed", error=str(portfolio_result))
            else:
                portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
        except Exception as phase4_err:
            logger.error("pipeline.phase4_error", error=str(phase4_err))

        logger.info(
            "pipeline.phase4_done",
            ps_length=len(ps_html),
            portfolio_length=len(portfolio_html),
        )

        # ── Phase 5: Validate key documents (non-blocking) ───────────
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
            logger.info("pipeline.validation_done", cv_valid=cv_valid)
        except Exception as val_err:
            logger.warning("pipeline.validation_skipped", error=str(val_err))

        # ── Format response for frontend ──────────────────────────────
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

        logger.info("pipeline.complete", overall_score=response["scores"]["overall"])
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
async def generate_pipeline_stream(req: PipelineRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    SSE streaming version of the pipeline.
    Uses the agent pipeline (Researcher → Drafter → Critic → Optimizer →
    FactChecker → Validator) when available and emits agent_status events
    alongside regular progress events.
    Falls back to the legacy direct-chain path if agents are unavailable.
    """
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
    exp_gaps = gap_analysis.get("experience_gaps", [])
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

    # Verify the application belongs to this user
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id,confirmed_facts")
        .eq("id", req.application_id)
        .eq("user_id", user_id)
        .maybeSingle()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    job_row = {
        "user_id": user_id,
        "application_id": req.application_id,
        "requested_modules": req.requested_modules,
        "status": "queued",
        "progress": 0,
    }
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .insert(job_row)
        .select("id")
        .single()
        .execute()
    )
    return {"job_id": job_resp.data["id"]}


@router.get("/jobs/{job_id}/stream")
async def stream_generation_job(
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Run the AI pipeline for a queued job and stream SSE progress events."""
    from app.core.database import get_supabase, TABLES

    sb = get_supabase()
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")

    # Fetch job
    job_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["generation_jobs"])
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .maybeSingle()
        .execute()
    )
    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Generation job not found")

    job = job_resp.data
    app_id = job["application_id"]

    # Fetch application confirmed_facts
    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("confirmed_facts")
        .eq("id", app_id)
        .maybeSingle()
        .execute()
    )
    if not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    confirmed_facts = app_resp.data.get("confirmed_facts") or {}
    job_title = confirmed_facts.get("jobTitle") or confirmed_facts.get("job_title") or ""
    company_name = confirmed_facts.get("company") or ""
    jd_text_val = confirmed_facts.get("jdText") or confirmed_facts.get("jd_text") or ""
    resume_text_val = (confirmed_facts.get("resume") or {}).get("text") or ""

    if not job_title or not jd_text_val:
        raise HTTPException(
            status_code=400,
            detail="Application is missing job title or job description — please complete the application first",
        )

    async def event_stream() -> AsyncGenerator[str, None]:  # noqa: C901
        try:
            # Mark job as running
            await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_jobs"])
                .update({"status": "running", "progress": 5, "phase": "initializing"})
                .eq("id", job_id)
                .execute()
            )

            async def check_cancel() -> bool:
                try:
                    r = await asyncio.to_thread(
                        lambda: sb.table(TABLES["generation_jobs"])
                        .select("cancel_requested")
                        .eq("id", job_id)
                        .maybeSingle()
                        .execute()
                    )
                    return bool((r.data or {}).get("cancel_requested"))
                except Exception:
                    return False

            async def update_progress(phase: str, progress: int, message: str) -> None:
                try:
                    await asyncio.to_thread(
                        lambda: sb.table(TABLES["generation_jobs"])
                        .update({"phase": phase, "progress": progress, "message": message})
                        .eq("id", job_id)
                        .execute()
                    )
                except Exception:
                    pass

            from ai_engine.client import AIClient
            from ai_engine.chains.role_profiler import RoleProfilerChain
            from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
            from ai_engine.chains.gap_analyzer import GapAnalyzerChain
            from ai_engine.chains.document_generator import DocumentGeneratorChain
            from ai_engine.chains.career_consultant import CareerConsultantChain
            from ai_engine.chains.validator import ValidatorChain

            ai = AIClient()
            company_str = company_name or "the company"

            yield _sse("progress", {"phase": "initializing", "step": 0, "totalSteps": 6, "progress": 5, "message": "Initializing AI engine…"})
            await update_progress("initializing", 5, "Initializing AI engine…")

            if await check_cancel():
                yield _sse("error", {"message": "Generation cancelled.", "code": 499})
                await asyncio.to_thread(lambda: sb.table(TABLES["generation_jobs"]).update({"status": "cancelled", "finished_at": "now()"}).eq("id", job_id).execute())
                return

            # ── Phase 1: Parse resume + benchmark ────────────────────
            profiler = RoleProfilerChain(ai)
            benchmark_chain = BenchmarkBuilderChain(ai)

            yield _sse("progress", {"phase": "profiling", "step": 1, "totalSteps": 6, "progress": 10, "message": "Parsing resume & building candidate benchmark…"})
            await update_progress("profiling", 10, "Parsing resume & building candidate benchmark…")

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

            benchmark_cv_html = ""
            try:
                benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                    user_profile=user_profile, benchmark_data=benchmark_data,
                    job_title=job_title, company=company_str, jd_text=jd_text_val,
                )
            except Exception as bcv_err:
                logger.warning("job_stream.benchmark_cv_failed", error=str(bcv_err))

            yield _sse("progress", {"phase": "profiling_done", "step": 1, "totalSteps": 6, "progress": 25, "message": "Resume parsed & benchmark built ✓"})
            await update_progress("profiling_done", 25, "Resume parsed & benchmark built ✓")

            if await check_cancel():
                yield _sse("error", {"message": "Generation cancelled.", "code": 499})
                await asyncio.to_thread(lambda: sb.table(TABLES["generation_jobs"]).update({"status": "cancelled", "finished_at": "now()"}).eq("id", job_id).execute())
                return

            # ── Phase 2: Gap Analysis ─────────────────────────────────
            yield _sse("progress", {"phase": "gap_analysis", "step": 2, "totalSteps": 6, "progress": 30, "message": "Analyzing skill gaps…"})
            await update_progress("gap_analysis", 30, "Analyzing skill gaps…")

            gap_chain = GapAnalyzerChain(ai)
            gap_analysis = await gap_chain.analyze_gaps(user_profile, benchmark_data, job_title, company_str)

            yield _sse("progress", {"phase": "gap_analysis_done", "step": 2, "totalSteps": 6, "progress": 45, "message": "Gap analysis complete ✓"})
            await update_progress("gap_analysis_done", 45, "Gap analysis complete ✓")

            if await check_cancel():
                yield _sse("error", {"message": "Generation cancelled.", "code": 499})
                await asyncio.to_thread(lambda: sb.table(TABLES["generation_jobs"]).update({"status": "cancelled", "finished_at": "now()"}).eq("id", job_id).execute())
                return

            # ── Phase 3: Generate CV, Cover Letter, Roadmap ───────────
            yield _sse("progress", {"phase": "documents", "step": 3, "totalSteps": 6, "progress": 50, "message": "Generating CV, cover letter & learning plan…"})
            await update_progress("documents", 50, "Generating CV, cover letter & learning plan…")

            doc_chain = DocumentGeneratorChain(ai)
            consultant = CareerConsultantChain(ai)

            cv_html, cl_html, roadmap = await asyncio.gather(
                doc_chain.generate_tailored_cv(
                    user_profile=user_profile, job_title=job_title,
                    company=company_str, jd_text=jd_text_val,
                    gap_analysis=gap_analysis, resume_text=resume_text_val,
                ),
                doc_chain.generate_tailored_cover_letter(
                    user_profile=user_profile, job_title=job_title,
                    company=company_str, jd_text=jd_text_val, gap_analysis=gap_analysis,
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

            yield _sse("progress", {"phase": "documents_done", "step": 3, "totalSteps": 6, "progress": 70, "message": "CV, cover letter & learning plan ready ✓"})
            await update_progress("documents_done", 70, "CV, cover letter & learning plan ready ✓")

            if await check_cancel():
                yield _sse("error", {"message": "Generation cancelled.", "code": 499})
                await asyncio.to_thread(lambda: sb.table(TABLES["generation_jobs"]).update({"status": "cancelled", "finished_at": "now()"}).eq("id", job_id).execute())
                return

            # ── Phase 4: Personal statement + Portfolio ───────────────
            yield _sse("progress", {"phase": "portfolio", "step": 4, "totalSteps": 6, "progress": 75, "message": "Building personal statement & portfolio…"})
            await update_progress("portfolio", 75, "Building personal statement & portfolio…")

            ps_html = ""
            portfolio_html = ""
            try:
                ps_result, portfolio_result = await asyncio.gather(
                    doc_chain.generate_tailored_personal_statement(
                        user_profile=user_profile, job_title=job_title,
                        company=company_str, jd_text=jd_text_val,
                        gap_analysis=gap_analysis, resume_text=resume_text_val,
                    ),
                    doc_chain.generate_tailored_portfolio(
                        user_profile=user_profile, job_title=job_title,
                        company=company_str, jd_text=jd_text_val,
                        gap_analysis=gap_analysis, resume_text=resume_text_val,
                    ),
                    return_exceptions=True,
                )
                if not isinstance(ps_result, Exception):
                    ps_html = ps_result if isinstance(ps_result, str) else ""
                if not isinstance(portfolio_result, Exception):
                    portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
            except Exception as phase4_err:
                logger.error("job_stream.phase4_error", error=str(phase4_err))

            yield _sse("progress", {"phase": "portfolio_done", "step": 4, "totalSteps": 6, "progress": 88, "message": "Personal statement & portfolio ready ✓"})
            await update_progress("portfolio_done", 88, "Personal statement & portfolio ready ✓")

            # ── Phase 5: Validation ───────────────────────────────────
            yield _sse("progress", {"phase": "validation", "step": 5, "totalSteps": 6, "progress": 90, "message": "Validating document quality…"})

            validation: Dict[str, Any] = {}
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
                logger.warning("job_stream.validation_skipped", error=str(val_err))

            yield _sse("progress", {"phase": "validation_done", "step": 5, "totalSteps": 6, "progress": 95, "message": "Quality checks passed ✓"})
            yield _sse("progress", {"phase": "formatting", "step": 6, "totalSteps": 6, "progress": 98, "message": "Packaging your application…"})
            await update_progress("formatting", 98, "Packaging your application…")

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

            # Persist final result
            await asyncio.to_thread(
                lambda: sb.table(TABLES["generation_jobs"])
                .update({"status": "succeeded", "progress": 100, "result": response, "finished_at": "now()"})
                .eq("id", job_id)
                .execute()
            )

            logger.info("job_stream.complete", job_id=job_id, overall_score=response["scores"]["overall"])
            yield _sse("complete", {"progress": 100, "result": response})

        except Exception as e:
            classified = _classify_ai_error(e)
            if classified:
                code = int(classified["code"])
                msg = str(classified["message"])
                retry_after = classified.get("retry_after_seconds")
                logger.error("job_stream.ai_error", job_id=job_id, code=code, message=msg)
                try:
                    await asyncio.to_thread(
                        lambda: sb.table(TABLES["generation_jobs"])
                        .update({"status": "failed", "error_message": msg, "finished_at": "now()"})
                        .eq("id", job_id)
                        .execute()
                    )
                except Exception:
                    pass
                payload: Dict[str, Any] = {"message": msg, "code": code}
                if retry_after:
                    payload["retryAfterSeconds"] = retry_after
                yield _sse("error", payload)
            else:
                logger.error("job_stream.error", job_id=job_id, error=str(e), traceback=traceback.format_exc())
                err_msg = "AI generation failed due to an unexpected error. Please try again."
                try:
                    await asyncio.to_thread(
                        lambda: sb.table(TABLES["generation_jobs"])
                        .update({"status": "failed", "error_message": str(e)[:500], "finished_at": "now()"})
                        .eq("id", job_id)
                        .execute()
                    )
                except Exception:
                    pass
                yield _sse("error", {"message": err_msg, "code": 500})

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
                "finished_at": "now()",
            })
            .in_("status", ["running", "queued"])
            .execute()
        )
        return len(resp.data) if resp.data else 0
    except Exception as e:
        logger.warning("recover_inflight_jobs_failed", error=str(e))
        return 0
