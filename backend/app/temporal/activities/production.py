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
from typing import Any, Optional

from app.temporal.activities import (
    ActivityHooks,
    CritiqueResult,
    GenerationInput,
    GenerationOutcome,
    GenerationPlan,
    GenerationStep,
    StepResult,
)
from app.temporal.checkpoints import CheckpointStore

logger = logging.getLogger("hirestack.temporal.production")

PIPELINE_STEP_NAME = "run_pipeline"

# Per-stage decomposition (ADR-0036, m8-pr32). Names match the runtime's
# PHASE_SLO_MS keys. The trailing ``persist`` runtime phase is folded into
# ``nova`` for checkpointing because it has no independent skip-if-done
# semantics (the runtime is upsert-idempotent on job_id at the persist step).
STAGE_ORDER: tuple[str, ...] = (
    "recon",
    "atlas",
    "cipher",
    "quill",
    "forge",
    "sentinel",
    "nova",
)

# Only the FIRST stage actually invokes the runtime end-to-end. The remaining
# stages skip-via-checkpoint because the runtime has already done their work
# in the same process. This is the m8-pr32 shipping reality; per-phase
# entrypoints land in m8-pr32b. See ADR-0036 §2 + §6 for the rollout plan.
_RUNTIME_DRIVING_STAGE = STAGE_ORDER[0]


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


# ============================================================================
#  Per-stage decomposition (ADR-0036, m8-pr32; flag ff_temporal_per_stage)
# ============================================================================

def _build_per_stage_plan(inp: GenerationInput) -> GenerationPlan:
    """Return a 7-step plan, one step per pipeline phase. Each step's
    ``arguments`` carries the original payload so the execute hook can
    inspect it without re-fetching state. The workflow loops over plan.steps
    in order; the checkpoint-aware execute hook decides per-step whether to
    run or skip based on the checkpoint table.
    """
    payload = dict(inp.payload or {})
    return GenerationPlan(
        steps=[GenerationStep(name=stage, arguments=dict(payload)) for stage in STAGE_ORDER]
    )


def _build_checkpoint_store() -> Optional[CheckpointStore]:
    """Lazily build a CheckpointStore. Returns None if Supabase isn't wired
    (e.g. unit tests that don't bring up the DB). The execute hook treats
    None the same as "no checkpoint store" — it always runs the work, no
    skip optimisation. This keeps the hook safe to import in any context.
    """
    try:
        from app.core.database import get_supabase  # local import: avoid hard dep at module load
        client = get_supabase()
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(
            "checkpoint_store_unavailable",
            extra={"error_class": exc.__class__.__name__, "error": str(exc)[:200]},
        )
        return None
    if client is None:
        return None
    return CheckpointStore(client)


async def _execute_with_checkpoint(
    inp: GenerationInput, step: GenerationStep
) -> StepResult:
    """Checkpoint-aware execute hook for the per-stage plan.

    Contract:
      1. Read the checkpoint for (job_id, step.name).
      2. If status='complete' → return cached StepResult; do NOT re-run.
         **This is the resume contract.**
      3. Otherwise: mark_running, dispatch the stage's work, then
         mark_complete on success or mark_failed on raise.
      4. Only the first stage drives the runtime end-to-end (m8-pr32 reality;
         see ADR-0036 §2). Subsequent stages are skip-via-checkpoint after
         the first stage marks them complete.
    """
    store = _build_checkpoint_store()

    if store is not None:
        existing = store.read(inp.job_id, step.name)
        if existing is not None and existing.status == "complete":
            logger.info(
                "temporal_activity.checkpoint.skip",
                extra={
                    "job_id": inp.job_id,
                    "stage": step.name,
                    "attempt_count": existing.attempt_count,
                },
            )
            return StepResult(
                step=step.name,
                output={
                    "job_id": inp.job_id,
                    "stage": step.name,
                    "resumed": True,
                    "summary": existing.output_summary or {},
                },
            )
        store.mark_running(inp.job_id, step.name)

    logger.info(
        "temporal_activity.per_stage.start",
        extra={"job_id": inp.job_id, "stage": step.name, "user_id": inp.user_id},
    )

    try:
        if step.name == _RUNTIME_DRIVING_STAGE:
            # First stage: run the legacy runtime end-to-end. Subsequent
            # stages are no-ops at the work level (they only flip the
            # checkpoint to 'complete' so resume sees them as done).
            from app.api.routes.generate.jobs import _run_generation_job_via_runtime
            await _run_generation_job_via_runtime(inp.job_id, inp.user_id)
            summary: dict[str, Any] = {
                "job_id": inp.job_id,
                "stage": step.name,
                "runtime_driven": True,
            }
        else:
            # Downstream stages: the runtime already did this work in the
            # first stage. Mark complete so a resumed worker would skip.
            # When m8-pr32b lands per-phase entrypoints, only this branch
            # changes (it dispatches to the per-phase callable).
            summary = {
                "job_id": inp.job_id,
                "stage": step.name,
                "runtime_driven": False,
                "folded_into": _RUNTIME_DRIVING_STAGE,
            }
    except Exception as exc:
        if store is not None:
            store.mark_failed(inp.job_id, step.name, exc.__class__.__name__)
        logger.warning(
            "temporal_activity.per_stage.failed",
            extra={
                "job_id": inp.job_id,
                "stage": step.name,
                "error_class": exc.__class__.__name__,
            },
        )
        raise

    if store is not None:
        store.mark_complete(inp.job_id, step.name, summary=summary)

    logger.info(
        "temporal_activity.per_stage.done",
        extra={"job_id": inp.job_id, "stage": step.name},
    )
    return StepResult(step=step.name, output=summary)


# ============================================================================
#  Hook builder — flag-aware
# ============================================================================

def _per_stage_flag_enabled() -> bool:
    """Read ``ff_temporal_per_stage`` defensively. Default OFF on any error."""
    try:
        from app.core.config import get_settings
        return bool(getattr(get_settings(), "ff_temporal_per_stage", False))
    except Exception:  # noqa: BLE001 — defensive default-off
        return False


def build_production_hooks() -> ActivityHooks:
    """Return ActivityHooks wired to the production generation pipeline.

    Flag-aware (ADR-0036, m8-pr32):
      * ``ff_temporal_per_stage`` ON  → 7-stage plan + checkpoint-aware execute.
      * ``ff_temporal_per_stage`` OFF → legacy single-step plan + direct runtime
        execute (zero behaviour change from m6-pr24).
    """
    if _per_stage_flag_enabled():
        return ActivityHooks(
            plan=_build_per_stage_plan,
            execute=_execute_with_checkpoint,
            critique=_critique_passthrough,
            persist=_persist_noop,
            emit_event=_emit_event_noop,
        )
    return ActivityHooks(
        plan=_build_plan,
        execute=_execute_via_runtime,
        critique=_critique_passthrough,
        persist=_persist_noop,
        emit_event=_emit_event_noop,
    )


__all__: list[str] = [
    "PIPELINE_STEP_NAME",
    "STAGE_ORDER",
    "build_production_hooks",
    "_build_per_stage_plan",
    "_execute_with_checkpoint",
]
