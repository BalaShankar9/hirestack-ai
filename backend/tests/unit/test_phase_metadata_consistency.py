"""S3-F5 — Phase metadata internal-consistency invariants.

DatabaseSink keeps three pieces of phase metadata that MUST stay in
lock-step or polling clients show wrong progress / wrong agent /
wrong total steps:

  1. `_PHASE_ORDER`  — list, drives `_phase_index` and `completed_steps`.
  2. `_PHASE_STEP`   — dict, 1-based step number per phase.
  3. `_phase_to_agent` mapping — phase → persona name shown in UI.
  4. `_TOTAL_STEPS`  — must equal `len(_PHASE_ORDER)`.

The whole class is the bug-magnet for future contributors who add a
new phase: forget to update one of these and the symptom is silent
wrong-progress in production. These tests catch it at CI.
"""
from __future__ import annotations

from app.services.pipeline_runtime import DatabaseSink


def _new_sink() -> DatabaseSink:
    from unittest.mock import MagicMock
    return DatabaseSink(
        db=MagicMock(),
        tables={
            "generation_jobs": "generation_jobs",
            "generation_job_events": "generation_job_events",
        },
        job_id="j", user_id="u", application_id="a",
    )


def test_phase_order_and_phase_step_have_identical_phases() -> None:
    """Every phase in _PHASE_ORDER must appear in _PHASE_STEP and
    vice-versa — adding a phase to one list without the other silently
    breaks completed_steps tracking."""
    assert set(DatabaseSink._PHASE_ORDER) == set(DatabaseSink._PHASE_STEP.keys())


def test_phase_step_numbers_are_1_based_and_dense() -> None:
    """_PHASE_STEP values must be 1..N with no gaps. completed_steps
    arithmetic depends on this."""
    values = sorted(DatabaseSink._PHASE_STEP.values())
    assert values == list(range(1, len(values) + 1))


def test_total_steps_matches_phase_order_length() -> None:
    assert DatabaseSink._TOTAL_STEPS == len(DatabaseSink._PHASE_ORDER)


def test_every_canonical_phase_has_an_agent_mapping() -> None:
    """Every phase in _PHASE_ORDER must produce a non-empty, non-default
    agent name from `_phase_to_agent`. A missing mapping silently falls
    through to the phase name itself, which is right today (recon → recon)
    but is the kind of thing that breaks when someone renames a phase."""
    sink = _new_sink()
    for phase in DatabaseSink._PHASE_ORDER:
        agent = sink._phase_to_agent(phase)
        assert agent and agent != "pipeline", (
            f"phase {phase!r} produced fallback agent {agent!r}"
        )


def test_initializing_phase_maps_to_recon_agent() -> None:
    """Pipeline emits `initializing` before recon kicks off; UI must
    show the recon persona during that window, not 'pipeline'."""
    assert _new_sink()._phase_to_agent("initializing") == "recon"


def test_unknown_phase_falls_back_to_phase_name_or_pipeline() -> None:
    sink = _new_sink()
    assert sink._phase_to_agent("ghost") == "ghost"
    assert sink._phase_to_agent("") == "pipeline"


def test_phase_index_returns_minus_one_for_unknown() -> None:
    sink = _new_sink()
    assert sink._phase_index("ghost") == -1
    assert sink._phase_index("recon") == 0
    assert sink._phase_index("nova") == 6
