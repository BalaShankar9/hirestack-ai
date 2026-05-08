"""Pin shared phase contracts for auxiliary orchestrators."""
from __future__ import annotations

import pytest

from ai_engine.agents.orchestration import (
    INTERVIEW_SESSION_PHASE_ORDER,
    PPT_GENERATION_PHASE_ORDER,
    PPT_RENDER_PHASE_ORDER,
    VIDEO_PITCH_PHASE_ORDER,
    TimedWorkflow,
    WorkflowPhaseStatus,
    get_workflow_phase_order,
    is_terminal_workflow_phase,
)


def test_aux_phase_orders_are_pinned() -> None:
    assert PPT_GENERATION_PHASE_ORDER == (
        "outline",
        "dataresearch",
        "contentenhancement",
        "aiimagegeneration",
        "qualityvalidation",
        "translation",
        "composition",
        "polish",
        "interactiveelements",
    )
    assert PPT_RENDER_PHASE_ORDER == (
        "dataresearch",
        "contentenhancement",
        "aiimagegeneration",
        "qualityvalidation",
        "translation",
        "composition",
        "polish",
        "interactiveelements",
    )
    assert VIDEO_PITCH_PHASE_ORDER == (
        "script_write",
        "avatar_submit",
        "tts_synthesize",
    )
    assert INTERVIEW_SESSION_PHASE_ORDER == (
        "question_planning",
        "tts_synthesize",
    )


def test_phase_order_lookup_and_terminal_checks() -> None:
    assert get_workflow_phase_order("video_pitch") == VIDEO_PITCH_PHASE_ORDER
    assert is_terminal_workflow_phase("video_pitch", "tts_synthesize") is True
    assert is_terminal_workflow_phase("video_pitch", "script_write") is False


@pytest.mark.asyncio
async def test_timed_workflow_enforces_known_phase_order() -> None:
    workflow = TimedWorkflow("video_pitch")

    await workflow.run_phase("script_write", lambda: _async_value("ok"))

    assert workflow.phase_statuses["script_write"] == WorkflowPhaseStatus.COMPLETED.value

    with pytest.raises(ValueError, match="Unknown phase"):
        await workflow.run_phase("unknown", lambda: _async_value("bad"))


@pytest.mark.asyncio
async def test_timed_workflow_marks_failed_phases() -> None:
    workflow = TimedWorkflow("interview_session")

    with pytest.raises(RuntimeError, match="boom"):
        await workflow.run_phase("question_planning", _explode)

    assert workflow.phase_statuses["question_planning"] == WorkflowPhaseStatus.FAILED.value


async def _async_value(value: str) -> str:
    return value


async def _explode() -> None:
    raise RuntimeError("boom")