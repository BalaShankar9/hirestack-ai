"""Tests for production ActivityHooks bridging the GenerationWorkflow
to the legacy generation runtime (PR m6-pr24)."""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.temporal.activities import (
    GenerationInput,
    GenerationOutcome,
    GenerationStep,
    StepResult,
    build_activities,
)
from app.temporal.activities.production import (
    PIPELINE_STEP_NAME,
    _build_plan,
    _critique_passthrough,
    _emit_event_noop,
    _execute_via_runtime,
    _persist_noop,
    build_production_hooks,
)


def _input(**overrides: Any) -> GenerationInput:
    base = GenerationInput(
        job_id="job-prod-1",
        org_id="org-1",
        user_id="user-1",
        document_type="application_bundle",
        payload={
            "application_id": "app-9",
            "requested_modules": ["resume", "cover_letter"],
        },
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_build_plan_returns_single_pipeline_step_with_payload():
    plan = _build_plan(_input())
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.name == PIPELINE_STEP_NAME
    assert step.arguments == {
        "application_id": "app-9",
        "requested_modules": ["resume", "cover_letter"],
    }


def test_build_plan_with_empty_payload_still_produces_one_step():
    inp = _input(payload={})
    plan = _build_plan(inp)
    assert len(plan.steps) == 1
    assert plan.steps[0].arguments == {}


def test_critique_passthrough_always_passes():
    verdict = _critique_passthrough(_input(), StepResult(step="x"))
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_persist_noop_returns_job_id_as_handle():
    inp = _input()
    handle = _persist_noop(inp, [StepResult(step=PIPELINE_STEP_NAME)])
    assert handle == inp.job_id


def test_emit_event_noop_does_not_raise():
    outcome = GenerationOutcome(
        job_id="job-prod-1",
        persisted_id="job-prod-1",
        steps=[StepResult(step=PIPELINE_STEP_NAME)],
    )
    # Must be silent; only logs.
    assert _emit_event_noop(outcome) is None


@pytest.mark.asyncio
async def test_execute_via_runtime_delegates_to_legacy_runtime():
    """The execute hook must call the legacy runtime entrypoint with
    the workflow's job_id + user_id, and return a StepResult tagged
    as delegated. The runtime call is async, so the hook is async too."""

    fake_runtime = AsyncMock(return_value=None)

    with patch(
        "app.api.routes.generate.jobs._run_generation_job_via_runtime",
        fake_runtime,
    ):
        result = await _execute_via_runtime(
            _input(),
            GenerationStep(name=PIPELINE_STEP_NAME, arguments={}),
        )

    fake_runtime.assert_awaited_once_with("job-prod-1", "user-1")
    assert result.step == PIPELINE_STEP_NAME
    assert result.output == {"job_id": "job-prod-1", "delegated": True}


def test_build_production_hooks_wires_all_five_callables():
    hooks = build_production_hooks()
    assert hooks.plan is _build_plan
    assert hooks.execute is _execute_via_runtime
    assert hooks.critique is _critique_passthrough
    assert hooks.persist is _persist_noop
    assert hooks.emit_event is _emit_event_noop


def test_build_activities_supports_async_execute_hook():
    """PR m6-pr24 also adds awaitable-aware activity bodies. Verify
    that build_activities(production_hooks) produces five Temporal
    activities and that the execute one is async (so awaiting an
    async hook works at runtime)."""
    activities = build_activities(build_production_hooks())
    assert len(activities) == 5
    names = {fn.__name__ for fn in activities}
    assert {"plan", "execute_step", "critique", "persist", "emit_event"} <= names
    # Every activity body is async — Temporal requires it.
    for fn in activities:
        assert inspect.iscoroutinefunction(fn), fn.__name__
