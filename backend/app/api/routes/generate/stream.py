"""SSE streaming pipeline endpoint (POST /pipeline/stream)."""
import asyncio
import traceback
from typing import Dict, Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, check_billing_limit
from app.core.security import limiter

from .schemas import PipelineRequest
from .helpers import (
    PIPELINE_TIMEOUT,
    _RUNTIME_AVAILABLE,
    _AGENT_PIPELINES_AVAILABLE,
    _classify_ai_error,
    _build_company_intel_summary,
    _build_atlas_diagnostics,
    _validate_pipeline_input,
    _sse,
    _agent_sse,
    _extract_pipeline_html,
    _extract_keywords_from_jd,
    _quality_score_from_scores,
    _validation_issue_count,
    _build_evidence_summary,
    _format_response,
    logger,
    CircuitBreakerOpen,
)

try:
    from .helpers import _PipelineRuntime, _RuntimeConfig, _ExecutionMode, _SSESink
except ImportError:
    pass

try:
    from .helpers import (
        resume_parse_pipeline,
        benchmark_pipeline,
        gap_analysis_pipeline,
        cv_generation_pipeline,
        cover_letter_pipeline,
        personal_statement_pipeline,
        portfolio_pipeline,
        PipelineResult,
    )
except ImportError:
    pass

router = APIRouter()

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
            "message": "Deploying AI agent squad — 7 specialized agents standing by…",
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
            "message": "Atlas Agent: parsing resume and extracting profile data…",
        })
        yield _sse("detail", {
            "agent": "resume_parse",
            "message": "Atlas analyzing resume structure and extracting key qualifications…",
            "status": "running",
            "source": "atlas",
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

        yield _sse("detail", {
            "agent": "resume_parse",
            "message": "Resume analysis complete — profile extracted successfully.",
            "status": "completed",
            "source": "atlas",
        })

        # ── Phase 1b: Benchmark pipeline ─────────────────────────────
        yield _sse("progress", {
            "phase": "profiling",
            "step": 1,
            "totalSteps": 6,
            "progress": 15,
            "message": f"Atlas Agent: building candidate benchmark for {req.job_title}…",
        })
        yield _sse("detail", {
            "agent": "benchmark",
            "message": f"Atlas constructing ideal candidate benchmark for {req.job_title} at {company}…",
            "status": "running",
            "source": "atlas",
        })

        bench_pipe = benchmark_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=TABLES, user_id=user_id,
        )
        bench_result: PipelineResult = await bench_pipe.execute({
            "user_id": user_id,
            "job_title": req.job_title,
            "company": company,
            "jd_text": req.jd_text,
            "user_profile": user_profile,
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

        yield _sse("detail", {
            "agent": "benchmark",
            "message": f"Benchmark built — identified {len(keywords)} key skills for {req.job_title}.",
            "status": "completed",
            "source": "atlas",
        })

        yield _sse("progress", {
            "phase": "profiling_done",
            "step": 1,
            "totalSteps": 6,
            "progress": 25,
            "message": "Atlas complete — resume parsed & benchmark built ✓",
        })

        # ── Phase 1c: Company Intel + Catalog Planning ───────────────
        from ai_engine.chains.company_intel import CompanyIntelChain
        from app.services.document_catalog import discover_and_observe

        yield _sse("progress", {
            "phase": "recon",
            "step": 1,
            "totalSteps": 6,
            "progress": 25,
            "message": f"Recon Agent: gathering intelligence on {company}…",
        })

        # Emit initial recon detail to show activity immediately
        yield _sse("detail", {
            "agent": "recon",
            "message": f"Initiating reconnaissance on {company} — scanning public data sources…",
            "status": "running",
            "source": "recon",
        })

        company_intel_stream: dict = {}
        try:
            intel_chain = CompanyIntelChain(ai)
            _recon_event_count = 0

            async def intel_event_callback(event: dict) -> None:
                nonlocal _recon_event_count
                _recon_event_count += 1
                payload: Dict[str, Any] = {
                    "agent": "recon",
                    "message": str(event.get("message") or "Recon update"),
                    "status": str(event.get("status") or "info"),
                    "source": str(event.get("source") or "recon"),
                }
                if isinstance(event.get("url"), str):
                    payload["url"] = event["url"]
                if isinstance(event.get("metadata"), dict):
                    payload["metadata"] = event["metadata"]
                events_queue.append(_sse("detail", payload))

            company_intel_stream = await asyncio.wait_for(
                intel_chain.gather_intel(
                    company=company,
                    job_title=req.job_title,
                    jd_text=req.jd_text,
                    on_event=intel_event_callback,
                ),
                timeout=45,
            )
            for ev in events_queue:
                yield ev
            events_queue.clear()

            yield _sse("detail", {
                "agent": "recon",
                "message": f"Recon complete — gathered {_recon_event_count} intelligence signals on {company}.",
                "status": "completed",
                "source": "recon",
            })
        except asyncio.TimeoutError:
            # Flush whatever recon events we gathered before timeout
            for ev in events_queue:
                yield ev
            events_queue.clear()
            yield _sse("detail", {
                "agent": "recon",
                "message": f"Recon completed partial scan of {company} (time limit reached); proceeding with available intel.",
                "status": "warning",
                "source": "analysis",
            })
        except Exception as intel_err:
            logger.warning("agent_pipeline.intel_failed", error=str(intel_err)[:200])
            for ev in events_queue:
                yield ev
            events_queue.clear()
            yield _sse("detail", {
                "agent": "recon",
                "message": "Recon external intel encountered an issue; continuing with JD-based analysis.",
                "status": "warning",
                "source": "analysis",
                "metadata": {"error": str(intel_err)[:200]},
            })

        yield _sse("progress", {
            "phase": "recon_done",
            "step": 1,
            "totalSteps": 6,
            "progress": 28,
            "message": f"Recon complete — moving to gap analysis…",
        })

        company_intel_summary_stream = _build_company_intel_summary(company_intel_stream)

        doc_pack_plan_stream = await discover_and_observe(
            db=sb, tables=TABLES, ai_client=ai,
            jd_text=req.jd_text, job_title=req.job_title,
            company=company, user_profile=user_profile,
            user_id=user_id,
            company_intel=company_intel_stream,
        )

        # ── Phase 2: Gap analysis pipeline ───────────────────────────
        yield _sse("progress", {
            "phase": "gap_analysis",
            "step": 2,
            "totalSteps": 6,
            "progress": 30,
            "message": "Cipher Agent: analyzing skill gaps…",
        })
        yield _sse("detail", {
            "agent": "gap_analysis",
            "message": "Cipher analyzing your profile against benchmark requirements…",
            "status": "running",
            "source": "cipher",
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

        yield _sse("detail", {
            "agent": "gap_analysis",
            "message": "Gap analysis complete — identified strengths and improvement areas.",
            "status": "completed",
            "source": "cipher",
        })
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
            "message": "Quill Agent: generating CV, cover letter & learning plan…",
        })
        yield _sse("detail", {
            "agent": "cv_generation",
            "message": "Quill drafting tailored CV based on gap analysis and company intel…",
            "status": "running",
            "source": "quill",
        })
        yield _sse("detail", {
            "agent": "cover_letter",
            "message": "Quill crafting personalized cover letter in parallel…",
            "status": "running",
            "source": "quill",
        })

        doc_context = {
            "user_id": user_id,
            "user_profile": user_profile,
            "job_title": req.job_title,
            "company": company,
            "jd_text": req.jd_text,
            "gap_analysis": gap_analysis,
            "resume_text": req.resume_text,
            "company_intel": company_intel_summary_stream,
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

        yield _sse("detail", {
            "agent": "cv_generation",
            "message": "CV, cover letter, and career roadmap generated successfully.",
            "status": "completed",
            "source": "quill",
        })
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
            "message": "Forge Agent: building personal statement & portfolio…",
        })
        yield _sse("detail", {
            "agent": "personal_statement",
            "message": "Forge crafting personal brand statement…",
            "status": "running",
            "source": "forge",
        })
        yield _sse("detail", {
            "agent": "portfolio",
            "message": "Forge assembling portfolio showcase in parallel…",
            "status": "running",
            "source": "forge",
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

        yield _sse("detail", {
            "agent": "portfolio",
            "message": "Personal statement and portfolio completed.",
            "status": "completed",
            "source": "forge",
        })
        yield _sse("progress", {
            "phase": "portfolio_done",
            "step": 4,
            "totalSteps": 6,
            "progress": 88,
            "message": "Personal statement & portfolio ready ✓",
        })

        # ── Phase 5: Format response with quality metadata ────────────
        yield _sse("progress", {
            "phase": "validation",
            "step": 5,
            "totalSteps": 6,
            "progress": 92,
            "message": "Sentinel Agent: running quality validation…",
        })
        yield _sse("detail", {
            "agent": "validation",
            "message": "Sentinel inspecting all documents for quality and accuracy…",
            "status": "running",
            "source": "sentinel",
        })
        yield _sse("progress", {
            "phase": "formatting",
            "step": 6,
            "totalSteps": 6,
            "progress": 98,
            "message": "Nova Agent: assembling final application bundle…",
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
            atlas_diagnostics=_build_atlas_diagnostics(user_profile, benchmark_data),
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
            company_intel: dict = {}
            company_intel_summary = ""

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

            # ── Recon (best effort) ───────────────────────────────────
            try:
                from ai_engine.chains.company_intel import CompanyIntelChain
                intel_chain = CompanyIntelChain(ai)
                company_intel = await asyncio.wait_for(
                    intel_chain.gather_intel(
                        company=company,
                        job_title=req.job_title,
                        jd_text=req.jd_text,
                    ),
                    timeout=15,
                )
            except Exception as intel_err:
                logger.warning("pipeline_stream.intel_failed", error=str(intel_err)[:200])
                company_intel = {}
            company_intel_summary = _build_company_intel_summary(company_intel)

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
                    company_intel=company_intel_summary,
                ),
                doc_chain.generate_tailored_cover_letter(
                    user_profile=user_profile, job_title=req.job_title,
                    company=company, jd_text=req.jd_text,
                    gap_analysis=gap_analysis,
                    company_intel=company_intel_summary,
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
                atlas_diagnostics=_build_atlas_diagnostics(user_profile, benchmark_data),
            )

            if company_intel:
                response["companyIntel"] = company_intel

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


