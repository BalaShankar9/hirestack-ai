"""Production ActivityHooks for the GenerationWorkflow (PR m6-pr24).

Bridges the Temporal workflow to the existing in-process generation
pipeline so that flipping ``ff_temporal_generation`` actually runs a
real generation job. This is intentionally a *thin* bridge: the heavy
lifting (DB writes, event emission, AIM RAG, etc.) is delegated to
``_run_generation_job_via_runtime`` so we don't fork the pipeline.

Design notes
------------
- The workflow currently models a single high-level step
  ``run_pipeline``. Per-module decomposition is a future PR; right
  now we want the strangler path to behave identically to the legacy
  in-process path while gaining Temporal's durable retry semantics
  and observability.
- ``persist`` and ``emit_event`` are intentional no-ops: the legacy
  runtime already persists module artefacts and emits SSE events.
  Re-publishing here would double-write.
- ``critique`` is also a pass-through. The critic loop inside the
  workflow is exercised by tests with custom hooks; production runs
  with critic disabled until PR-25 wires a real reviewer.
- All activity bodies must remain *idempotent* under Temporal retry.
  The legacy runtime is itself idempotent on ``job_id`` so a retried
  ``execute`` call resumes / no-ops appropriately.
"""

from __future__ import annotations

import logging
from typing import Any

from app.temporal.activities import (
    ActivityHooks,
    CritiqueResult,
    GenerationInput,
    GenerationOutcome,
    GenerationPlan,
    GenerationStep,
    StepResult,
)

logger = logging.getLogger("hirestack.temporal.production")

PIPELINE_STEP_NAME = "run_pipeline"


def _build_plan(inp: GenerationInput) -> GenerationPlan:
    """Single-step plan that delegates the entire job to the legacy
    runtime. Step.arguments carries the original payload so the
    execute hook has everything it needs without re-fetching.
    """
    return GenerationPlan(
        steps=[
            GenerationStep(
                name=PIPELINE_STEP_NAME,
                arguments=dict(inp.payload or {}),
            )
        ]
    )


async def _execute_via_runtime(
    inp: GenerationInput, step: GenerationStep
) -> StepResult:
    """Run the legacy generation pipeline end-to-end for ``inp.job_id``.

    We import the runtime entrypoint lazily to keep the activities
    module importable from places that don't have the FastAPI app
    fully wired (e.g. unit tests that only build the workflow).
    """
    from app.api.routes.generate.jobs import _run_generation_job_via_runtime

    logger.info(
        "temporal_activity.execute.start",
        extra={"job_id": inp.job_id, "user_id": inp.user_id, "step": step.name},
    )
    await _run_generation_job_via_runtime(inp.job_id, inp.user_id)
    logger.info(
        "temporal_activity.execute.done",
        extra={"job_id": inp.job_id, "step": step.name},
    )
    return StepResult(
        step=step.name,
        output={"job_id": inp.job_id, "delegated": True},
    )


def _critique_passthrough(inp: GenerationInput, result: StepResult) -> CritiqueResult:
    return CritiqueResult(passed=True, score=1.0, reason="passthrough")


def _persist_noop(inp: GenerationInput, results: list[StepResult]) -> str:
    """The legacy runtime already persists artefacts. Return the
    job id as a stable handle so the workflow has something to log."""
    return inp.job_id


def _emit_event_noop(outcome: GenerationOutcome) -> None:
    """The legacy runtime already emits SSE/outbox events. We log a
    workflow-completion breadcrumb but do not double-publish."""
    logger.info(
        "temporal_activity.emit_event.workflow_complete",
        extra={
            "job_id": outcome.job_id,
            "persisted_id": outcome.persisted_id,
            "step_count": len(outcome.steps),
        },
    )


def build_production_hooks() -> ActivityHooks:
    """Return ActivityHooks wired to the production generation pipeline."""
    return ActivityHooks(
        plan=_build_plan,
        execute=_execute_via_runtime,
        critique=_critique_passthrough,
        persist=_persist_noop,
        emit_event=_emit_event_noop,
    )


__all__: list[str] = [
    "PIPELINE_STEP_NAME",
    "build_production_hooks",
]
