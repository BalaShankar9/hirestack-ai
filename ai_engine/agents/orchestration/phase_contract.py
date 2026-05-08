"""Canonical phase contracts for non-document agent orchestrators."""
from __future__ import annotations

from enum import Enum


class WorkflowPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


PPT_GENERATION_PHASE_ORDER: tuple[str, ...] = (
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

PPT_RENDER_PHASE_ORDER: tuple[str, ...] = (
    "dataresearch",
    "contentenhancement",
    "aiimagegeneration",
    "qualityvalidation",
    "translation",
    "composition",
    "polish",
    "interactiveelements",
)

VIDEO_PITCH_PHASE_ORDER: tuple[str, ...] = (
    "script_write",
    "avatar_submit",
    "tts_synthesize",
)

INTERVIEW_SESSION_PHASE_ORDER: tuple[str, ...] = (
    "question_planning",
    "tts_synthesize",
)


WORKFLOW_PHASE_ORDERS: dict[str, tuple[str, ...]] = {
    "ppt_generation": PPT_GENERATION_PHASE_ORDER,
    "ppt_generate_from_deck": PPT_RENDER_PHASE_ORDER,
    "video_pitch": VIDEO_PITCH_PHASE_ORDER,
    "interview_session": INTERVIEW_SESSION_PHASE_ORDER,
}


def get_workflow_phase_order(workflow_name: str) -> tuple[str, ...]:
    return WORKFLOW_PHASE_ORDERS.get(workflow_name, ())


def is_terminal_workflow_phase(workflow_name: str, phase_name: str) -> bool:
    order = get_workflow_phase_order(workflow_name)
    return bool(order) and phase_name == order[-1]