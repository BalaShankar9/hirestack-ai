"""Planner-driven pipeline endpoint (POST /pipeline/planned)."""
import asyncio
import traceback
import structlog
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user, check_billing_limit
from app.core.security import limiter

from .schemas import PlannedPipelineRequest
from .helpers import (
    MAX_JD_SIZE,
    MAX_RESUME_SIZE,
    PIPELINE_TIMEOUT,
    _classify_ai_error,
    logger,
    CircuitBreakerOpen,
)

router = APIRouter()

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
    if len(req.user_request) > 10_000:
        raise HTTPException(status_code=413, detail="user_request too large (max 10KB)")
    if len(req.jd_text) > MAX_JD_SIZE:
        raise HTTPException(status_code=413, detail="Job description too large (max 50KB)")
    if len(req.resume_text) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="Resume text too large (max 100KB)")

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
