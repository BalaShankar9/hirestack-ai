"""Canonical stage contract for the agent pipeline.

This module is the single source of truth for the per-document agent
stage order. It MUST stay in sync with the orchestrator
(``ai_engine/agents/orchestrator.py::AgentPipeline._execute_pipeline_stages``)
and the frontend timeline rail
(``frontend/src/components/workspace/agent-timeline-rail.tsx::STAGE_ORDER``).

History
-------
S13: ``optimizer_final_analysis`` was added to the orchestrator (Brief 1)
but the helper at ``backend/app/api/routes/generate/helpers.py`` was not
updated, so resume-point logic computed by ``get_resume_point()`` would
under-count completed stages when a job was interrupted at
``optimizer_final_analysis``. S14-F1 lifts the tuple here so the drift
cannot recur.
"""
from __future__ import annotations

# Per-document stages, in execution order.
#
# Each name MUST match the ``stage`` field used by ``stage_callback`` in
# ``orchestrator.py`` and the SSE ``event: agent_status`` payload's
# ``stage`` key. Renaming or reordering is a wire-protocol change.
DOCUMENT_STAGE_ORDER: tuple[str, ...] = (
    "researcher",
    "drafter",
    "critic",
    "optimizer",
    "fact_checker",
    "optimizer_final_analysis",
    "validator",
)


# Phase-level order used by ``PipelineRuntime`` for cross-document
# choreography (recon → atlas → cipher → quill → forge → sentinel → nova).
# Document stages run inside ``quill``/``forge``.
RUNTIME_PHASE_ORDER: tuple[str, ...] = (
    "recon",
    "atlas",
    "cipher",
    "quill",
    "forge",
    "sentinel",
    "nova",
)


def is_terminal_stage(stage: str) -> bool:
    """Return True if ``stage`` is the last per-document stage."""
    return stage == DOCUMENT_STAGE_ORDER[-1]
