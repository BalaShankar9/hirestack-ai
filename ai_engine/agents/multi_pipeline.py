"""
Multi-pipeline executor — runs a PipelinePlan produced by PlannerAgent.

Handles:
  • Sequential dependencies (topological ordering)
  • Parallel execution of independent steps
  • Context forwarding between dependent pipelines
  • Aggregation of results from all steps
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from ai_engine.agents.planner import PipelinePlan, PipelineStep
from ai_engine.agents.pipelines import build_pipeline
from ai_engine.agents.orchestrator import PipelineResult
from ai_engine.client import AIClient

logger = logging.getLogger("hirestack.multi_pipeline")


async def execute_plan(
    plan: PipelinePlan,
    context: dict,
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
) -> dict:
    """Execute a PipelinePlan and return aggregated results.

    Returns:
        {
            "results": {pipeline_name: PipelineResult, ...},
            "plan": plan dict,
            "total_latency_ms": int,
            "primary_result": PipelineResult,  # last step's result
        }
    """
    start = time.perf_counter()
    results: dict[str, PipelineResult] = {}

    # Build execution layers via topological sort
    layers = _topological_layers(plan.steps)

    for layer in layers:
        if len(layer) == 1:
            # Single step — run directly
            step = layer[0]
            step_result = await _run_step(
                step, context, results,
                ai_client=ai_client,
                on_stage_update=on_stage_update,
                db=db, tables=tables,
            )
            results[step.pipeline_name] = step_result
        else:
            # Multiple independent steps — run concurrently
            tasks = [
                _run_step(
                    step, context, results,
                    ai_client=ai_client,
                    on_stage_update=on_stage_update,
                    db=db, tables=tables,
                )
                for step in layer
            ]
            layer_results = await asyncio.gather(*tasks, return_exceptions=True)
            for step, result in zip(layer, layer_results):
                if isinstance(result, Exception):
                    logger.error(
                        "multi_pipeline_step_failed",
                        pipeline=step.pipeline_name,
                        error=str(result),
                    )
                    # Store a minimal error result
                    results[step.pipeline_name] = PipelineResult(
                        content={"error": str(result)},
                        quality_scores={},
                        optimization_report={},
                        fact_check_report={},
                        iterations_used=0,
                        total_latency_ms=0,
                        trace_id="",
                    )
                else:
                    results[step.pipeline_name] = result

    total_latency = int((time.perf_counter() - start) * 1000)

    # The primary result is the last step (or the last layer's first step)
    last_step_name = plan.steps[-1].pipeline_name if plan.steps else None
    primary_result = results.get(last_step_name) if last_step_name else None

    logger.info(
        "multi_pipeline_complete",
        pipelines=list(results.keys()),
        total_latency_ms=total_latency,
    )

    return {
        "results": results,
        "plan": {
            "steps": [
                {"pipeline_name": s.pipeline_name, "reason": s.reason}
                for s in plan.steps
            ],
            "reasoning": plan.reasoning,
        },
        "total_latency_ms": total_latency,
        "primary_result": primary_result,
    }


async def _run_step(
    step: PipelineStep,
    base_context: dict,
    prior_results: dict[str, PipelineResult],
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
) -> PipelineResult:
    """Run a single pipeline step, merging upstream outputs into context."""
    # Build context: start with base, merge outputs from dependencies
    step_context = dict(base_context)

    for dep_name in step.depends_on:
        dep_result = prior_results.get(dep_name)
        if dep_result and dep_result.content:
            # Store upstream result under a prefixed key
            step_context[f"_upstream_{dep_name}"] = dep_result.content
            # For gap_analysis → doc gen, merge gap data into top-level context
            if dep_name == "gap_analysis" and isinstance(dep_result.content, dict):
                step_context["gap_analysis"] = dep_result.content
            elif dep_name == "benchmark" and isinstance(dep_result.content, dict):
                step_context["benchmark"] = dep_result.content
            elif dep_name == "resume_parse" and isinstance(dep_result.content, dict):
                step_context["user_profile"] = dep_result.content

    # Apply any context overrides from the plan
    step_context.update(step.context_overrides)

    pipeline = build_pipeline(
        name=step.pipeline_name,
        ai_client=ai_client,
        on_stage_update=on_stage_update,
        db=db,
        tables=tables,
    )

    logger.info("multi_pipeline_step_start", pipeline=step.pipeline_name)
    result = await pipeline.execute(step_context)
    logger.info(
        "multi_pipeline_step_complete",
        pipeline=step.pipeline_name,
        latency_ms=result.total_latency_ms,
    )
    return result


def _topological_layers(steps: list[PipelineStep]) -> list[list[PipelineStep]]:
    """Group steps into layers where each layer's dependencies are satisfied
    by prior layers. Steps within a layer can run in parallel."""
    if not steps:
        return []

    step_map = {s.pipeline_name: s for s in steps}
    completed: set[str] = set()
    layers: list[list[PipelineStep]] = []

    remaining = list(steps)
    max_iterations = len(steps) + 1  # safety bound

    for _ in range(max_iterations):
        if not remaining:
            break

        # Find steps whose dependencies are all completed
        ready = [
            s for s in remaining
            if all(d in completed for d in s.depends_on)
        ]

        if not ready:
            # Circular dependency or missing deps — just run remaining sequentially
            logger.warning(
                "topological_sort_fallback",
                remaining=[s.pipeline_name for s in remaining],
            )
            for s in remaining:
                layers.append([s])
            break

        layers.append(ready)
        completed.update(s.pipeline_name for s in ready)
        remaining = [s for s in remaining if s.pipeline_name not in completed]

    return layers
