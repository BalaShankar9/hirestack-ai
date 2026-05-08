"""End-to-end test for GenerationWorkflow using the in-process
WorkflowEnvironment (PR m6-pr17). No Temporal server required."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal.activities import (
    ActivityHooks,
    CritiqueResult,
    GenerationInput,
    GenerationPlan,
    GenerationStep,
    StepResult,
    build_activities,
)
from app.temporal.workflows import GenerationWorkflow

TASK_QUEUE = "test-hirestack-generation"


def _input(**overrides) -> GenerationInput:
    base = GenerationInput(
        job_id="job-1",
        org_id="org-1",
        user_id="user-1",
        document_type="resume",
    )
    for k, v in overrides.items():
        base = replace(base, **{k: v})
    return base


async def _run(env, hooks: ActivityHooks, inp: GenerationInput):
    client: Client = env.client
    task_queue = f"test-hirestack-generation-{uuid.uuid4()}"
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[GenerationWorkflow],
        activities=build_activities(hooks),
    ):
        return await client.execute_workflow(
            GenerationWorkflow.run,
            inp,
            id=f"wf-{uuid.uuid4()}",
            task_queue=task_queue,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_happy_path_persists_and_emits(temporal_env) -> None:
    emitted: list = []
    hooks = ActivityHooks(emit_event=lambda outcome: emitted.append(outcome))
    outcome = await _run(temporal_env, hooks, _input())
    assert outcome.persisted_id == "doc_job-1"
    assert len(outcome.steps) == 1
    assert outcome.steps[0].step == "draft_resume"
    assert len(emitted) == 1 and emitted[0].job_id == "job-1"


@pytest.mark.asyncio(loop_scope="session")
async def test_multi_step_plan_runs_each_step(temporal_env) -> None:
    plan = GenerationPlan(steps=[
        GenerationStep(name="step_a"),
        GenerationStep(name="step_b"),
        GenerationStep(name="step_c"),
    ])
    hooks = ActivityHooks(plan=lambda inp: plan)
    outcome = await _run(temporal_env, hooks, _input())
    assert [s.step for s in outcome.steps] == ["step_a", "step_b", "step_c"]


@pytest.mark.asyncio(loop_scope="session")
async def test_critic_loop_retries_then_passes(temporal_env) -> None:
    attempts: list[int] = []

    def critique(inp, result):
        attempts.append(1)
        return CritiqueResult(passed=len(attempts) >= 2, reason="not_yet")

    hooks = ActivityHooks(critique=critique)
    outcome = await _run(temporal_env, hooks, _input())
    assert len(attempts) == 2
    assert outcome.persisted_id == "doc_job-1"


@pytest.mark.asyncio(loop_scope="session")
async def test_critic_gives_up_after_max_attempts(temporal_env) -> None:
    persists: list = []

    def critique(inp, result):
        return CritiqueResult(passed=False, reason="bad")

    hooks = ActivityHooks(
        critique=critique,
        persist=lambda inp, results: persists.append(results) or "should_not_happen",
    )
    with pytest.raises(Exception) as excinfo:
        await _run(temporal_env, hooks, _input())
    # Temporal wraps user exceptions as WorkflowFailureError; the
    # CriticGaveUp message lands on the .cause chain.
    err = excinfo.value
    messages: list[str] = []
    while err is not None:
        messages.append(getattr(err, "message", "") or str(err))
        err = getattr(err, "cause", None) or err.__cause__
    blob = " | ".join(messages)
    assert "step=draft_resume" in blob, blob
    assert persists == []


@pytest.mark.asyncio(loop_scope="session")
async def test_step_result_carries_execute_output(temporal_env) -> None:
    hooks = ActivityHooks(
        execute=lambda inp, step: StepResult(step=step.name, output={"chars": 42}),
    )
    outcome = await _run(temporal_env, hooks, _input())
    assert outcome.steps[0].output == {"chars": 42}


def test_settings_disabled_when_host_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.temporal.config import load_settings
    monkeypatch.delenv("TEMPORAL_HOST", raising=False)
    cfg = load_settings()
    assert cfg.enabled is False
    assert cfg.task_queue == "hirestack-generation"


def test_settings_enabled_when_host_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.temporal.config import load_settings
    monkeypatch.setenv("TEMPORAL_HOST", "temporal:7233")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "hirestack")
    cfg = load_settings()
    assert cfg.enabled is True
    assert cfg.namespace == "hirestack"
