"""Tests for the per-stage Temporal activity decomposition (ADR-0036, m8-pr32).

Covers:
- ``_build_per_stage_plan`` returns 7 stages in canonical order with payload.
- Hook builder picks per-stage plan when ``ff_temporal_per_stage`` is ON.
- Hook builder falls back to legacy single-step plan when flag is OFF.
- ``_execute_with_checkpoint`` skips on status='complete' (resume contract).
- ``_execute_with_checkpoint`` runs runtime on the first stage and folds
  remaining stages into checkpoint-only writes.
- ``_execute_with_checkpoint`` marks failed on raise.
- Missing checkpoint store does not block execution.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.temporal.activities import GenerationInput, GenerationStep
from app.temporal.activities.production import (
    PIPELINE_STEP_NAME,
    STAGE_ORDER,
    _build_per_stage_plan,
    _execute_with_checkpoint,
    build_production_hooks,
)
from app.temporal.checkpoints import Checkpoint


def _input(**overrides: Any) -> GenerationInput:
    base = GenerationInput(
        job_id="job-stage-1",
        org_id="org-1",
        user_id="user-1",
        document_type="application_bundle",
        payload={"application_id": "app-9", "requested_modules": ["resume"]},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ── _build_per_stage_plan ─────────────────────────────────────────────────

def test_build_per_stage_plan_returns_seven_stages_in_order():
    plan = _build_per_stage_plan(_input())
    assert [s.name for s in plan.steps] == list(STAGE_ORDER)
    assert len(plan.steps) == 7


def test_build_per_stage_plan_propagates_payload_to_every_step():
    plan = _build_per_stage_plan(_input())
    for step in plan.steps:
        assert step.arguments == {
            "application_id": "app-9",
            "requested_modules": ["resume"],
        }


def test_build_per_stage_plan_handles_empty_payload():
    plan = _build_per_stage_plan(_input(payload={}))
    assert all(step.arguments == {} for step in plan.steps)


def test_build_per_stage_plan_steps_are_independent_dicts():
    """Mutating one step.arguments must not bleed into siblings (defensive
    copy semantics — important if later stages annotate their own args)."""
    plan = _build_per_stage_plan(_input())
    plan.steps[0].arguments["mutated"] = True
    assert "mutated" not in plan.steps[1].arguments


# ── build_production_hooks (flag-aware) ───────────────────────────────────

def test_build_production_hooks_uses_legacy_plan_when_flag_off():
    with patch(
        "app.temporal.activities.production._per_stage_flag_enabled",
        return_value=False,
    ):
        hooks = build_production_hooks()
    plan = hooks.plan(_input())
    assert len(plan.steps) == 1
    assert plan.steps[0].name == PIPELINE_STEP_NAME


def test_build_production_hooks_uses_per_stage_plan_when_flag_on():
    with patch(
        "app.temporal.activities.production._per_stage_flag_enabled",
        return_value=True,
    ):
        hooks = build_production_hooks()
    plan = hooks.plan(_input())
    assert [s.name for s in plan.steps] == list(STAGE_ORDER)


def test_build_production_hooks_critique_persist_emit_unchanged_when_flag_on():
    """Only plan + execute should differ between flag states. The other
    three hooks remain the same passthrough/no-op functions to avoid
    accidental behaviour change."""
    with patch(
        "app.temporal.activities.production._per_stage_flag_enabled",
        return_value=False,
    ):
        legacy = build_production_hooks()
    with patch(
        "app.temporal.activities.production._per_stage_flag_enabled",
        return_value=True,
    ):
        per_stage = build_production_hooks()
    assert legacy.critique is per_stage.critique
    assert legacy.persist is per_stage.persist
    assert legacy.emit_event is per_stage.emit_event


# ── _execute_with_checkpoint: resume contract ─────────────────────────────

@pytest.mark.asyncio
async def test_execute_with_checkpoint_skips_when_status_complete():
    """The resume contract: a stage already marked complete must NOT
    re-invoke the runtime. Returns the cached summary."""
    fake_store = AsyncMock()
    fake_store.read.return_value = Checkpoint(
        job_id="job-stage-1",
        stage="recon",
        status="complete",
        attempt_count=1,
        output_summary={"runtime_driven": True},
    )
    # AsyncMock makes .read async; switch to MagicMock for sync methods
    from unittest.mock import MagicMock
    sync_store = MagicMock()
    sync_store.read.return_value = fake_store.read.return_value

    fake_runtime = AsyncMock()

    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=sync_store,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        result = await _execute_with_checkpoint(
            _input(),
            GenerationStep(name="recon", arguments={}),
        )

    fake_runtime.assert_not_awaited()
    sync_store.mark_running.assert_not_called()
    sync_store.mark_complete.assert_not_called()
    assert result.step == "recon"
    assert result.output["resumed"] is True
    assert result.output["summary"] == {"runtime_driven": True}


@pytest.mark.asyncio
async def test_execute_with_checkpoint_runs_runtime_on_first_stage_and_marks_complete():
    """First stage drives the runtime end-to-end and writes a checkpoint."""
    from unittest.mock import MagicMock
    sync_store = MagicMock()
    sync_store.read.return_value = None  # no prior checkpoint

    fake_runtime = AsyncMock(return_value=None)

    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=sync_store,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        result = await _execute_with_checkpoint(
            _input(),
            GenerationStep(name=STAGE_ORDER[0], arguments={}),
        )

    fake_runtime.assert_awaited_once_with("job-stage-1", "user-1")
    sync_store.mark_running.assert_called_once_with("job-stage-1", STAGE_ORDER[0])
    sync_store.mark_complete.assert_called_once()
    args, kwargs = sync_store.mark_complete.call_args
    assert args[0] == "job-stage-1"
    assert args[1] == STAGE_ORDER[0]
    assert kwargs["summary"]["runtime_driven"] is True
    assert result.output["runtime_driven"] is True


@pytest.mark.asyncio
async def test_execute_with_checkpoint_skips_runtime_for_downstream_stages():
    """Stages 2-7 must NOT re-invoke the runtime (m8-pr32 reality:
    runtime work is folded into the first stage; downstream stages only
    write checkpoints so a resumed worker would skip)."""
    from unittest.mock import MagicMock
    sync_store = MagicMock()
    sync_store.read.return_value = None

    fake_runtime = AsyncMock()

    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=sync_store,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        result = await _execute_with_checkpoint(
            _input(),
            GenerationStep(name="quill", arguments={}),
        )

    fake_runtime.assert_not_awaited()
    sync_store.mark_complete.assert_called_once()
    summary = sync_store.mark_complete.call_args.kwargs["summary"]
    assert summary["runtime_driven"] is False
    assert summary["folded_into"] == STAGE_ORDER[0]
    assert result.output["runtime_driven"] is False


@pytest.mark.asyncio
async def test_execute_with_checkpoint_marks_failed_and_reraises_on_runtime_exception():
    from unittest.mock import MagicMock
    sync_store = MagicMock()
    sync_store.read.return_value = None

    fake_runtime = AsyncMock(side_effect=RuntimeError("kaboom"))

    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=sync_store,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        with pytest.raises(RuntimeError, match="kaboom"):
            await _execute_with_checkpoint(
                _input(),
                GenerationStep(name=STAGE_ORDER[0], arguments={}),
            )

    sync_store.mark_failed.assert_called_once_with(
        "job-stage-1", STAGE_ORDER[0], "RuntimeError"
    )
    sync_store.mark_complete.assert_not_called()


@pytest.mark.asyncio
async def test_execute_with_checkpoint_works_when_store_unavailable():
    """If Supabase isn't wired (CheckpointStore=None), the activity must
    still run and return — just without skip-optimisation. Defensive
    default keeps the activity safe to import in any context."""
    fake_runtime = AsyncMock(return_value=None)

    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=None,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        result = await _execute_with_checkpoint(
            _input(),
            GenerationStep(name=STAGE_ORDER[0], arguments={}),
        )

    fake_runtime.assert_awaited_once_with("job-stage-1", "user-1")
    assert result.output["runtime_driven"] is True


# ── Resume scenario: mid-pipeline crash + retry ───────────────────────────

@pytest.mark.asyncio
async def test_resume_after_crash_skips_completed_stages_and_runs_only_remaining():
    """Integration-flavoured test of the resume contract.

    Scenario:
      * Stage 0 (recon)   -> previously completed (worker crashed AFTER mark_complete).
      * Stage 1 (atlas)   -> previously running (in-flight when crash hit).
      * Stages 2-6        -> never started.

    A retry must:
      * Skip stage 0 (return cached summary, no runtime call).
      * Re-run stage 1 (mark_running increments attempt, runtime not invoked
        because atlas is downstream-folded under m8-pr32 reality).
      * Process stages 2-6 normally.

    This proves the checkpoint table is the source of truth for "already
    done" and that a worker resuming the workflow does not re-burn cost
    for completed stages.
    """
    from unittest.mock import MagicMock

    # In-memory checkpoint state
    state: dict[tuple[str, str], Checkpoint] = {
        ("job-X", "recon"): Checkpoint(
            job_id="job-X",
            stage="recon",
            status="complete",
            attempt_count=1,
            output_summary={"runtime_driven": True},
        ),
        ("job-X", "atlas"): Checkpoint(
            job_id="job-X",
            stage="atlas",
            status="running",
            attempt_count=1,
        ),
    }

    sync_store = MagicMock()

    def _read(job_id: str, stage: str) -> Checkpoint | None:
        return state.get((job_id, stage))

    def _mark_running(job_id: str, stage: str) -> None:
        existing = state.get((job_id, stage))
        attempt = (existing.attempt_count + 1) if existing else 1
        state[(job_id, stage)] = Checkpoint(
            job_id=job_id, stage=stage, status="running", attempt_count=attempt
        )

    def _mark_complete(job_id: str, stage: str, summary: dict[str, Any] | None = None) -> None:
        existing = state.get((job_id, stage))
        attempt = existing.attempt_count if existing else 1
        state[(job_id, stage)] = Checkpoint(
            job_id=job_id,
            stage=stage,
            status="complete",
            attempt_count=attempt,
            output_summary=summary,
        )

    sync_store.read.side_effect = _read
    sync_store.mark_running.side_effect = _mark_running
    sync_store.mark_complete.side_effect = _mark_complete

    inp = GenerationInput(
        job_id="job-X",
        org_id="org-X",
        user_id="user-X",
        document_type="application_bundle",
        payload={},
    )
    fake_runtime = AsyncMock(return_value=None)

    results = []
    with patch(
        "app.temporal.activities.production._build_checkpoint_store",
        return_value=sync_store,
    ), patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        for stage in STAGE_ORDER:
            res = await _execute_with_checkpoint(
                inp, GenerationStep(name=stage, arguments={})
            )
            results.append(res)

    # Stage 0 (recon) was complete: no runtime call, returned cached.
    assert results[0].output.get("resumed") is True

    # The runtime was never called during this resume pass — recon was
    # cached, atlas+rest are downstream-folded. (When m8-pr32b lands per-phase
    # entrypoints, atlas will gain its own runtime call here.)
    fake_runtime.assert_not_called()

    # Atlas: mark_running got called (incrementing attempt_count to 2),
    # then mark_complete got called.
    assert state[("job-X", "atlas")].status == "complete"
    assert state[("job-X", "atlas")].attempt_count == 2

    # Stages 2-6: all marked complete (started fresh at attempt_count=1).
    for stage in STAGE_ORDER[2:]:
        assert state[("job-X", stage)].status == "complete"
        assert state[("job-X", stage)].attempt_count == 1
