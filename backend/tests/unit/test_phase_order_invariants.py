"""
Phase ordering & timing invariant tests for `PipelineRuntime`.

The 7-phase pipeline order (recon → atlas → cipher → quill → forge →
sentinel → nova) is the spine of every dashboard, replay view, and
SLA report this platform produces. Reordering phases — or adding /
removing one without updating sibling structures (PHASE_SLO_MS, the
`_phase_to_agent` map, the frontend's progress bar) — silently breaks
those downstream consumers because they all index by phase name.

These tests pin three intertwined invariants:

  1. Phase ORDER is canonical and stable across the codebase.
     `_PHASE_ORDER`, `_phase_index`, `_phase_to_agent`, and `PHASE_SLO_MS`
     must all agree on the same set of phase names.

  2. Phase TIMING is monotonic and durable.
     `_begin_phase` / `_finish_phase` write to `_phase_latencies`;
     calling `_finish_phase` without a prior `_begin_phase` MUST NOT
     emit a negative or wildly large duration.

  3. SLO budgets exist for every phase that runs.
     Every name in `_PHASE_ORDER` (plus the post-pipeline 'persist'
     step) must have a `PHASE_SLO_MS` entry, otherwise the slow-phase
     warning silently disappears.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.services.pipeline_runtime import (
    PHASE_SLO_MS,
    CollectorSink,
    DatabaseSink,
    ExecutionMode,
    PipelineRuntime,
    RuntimeConfig,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _runtime() -> PipelineRuntime:
    cfg = RuntimeConfig(mode=ExecutionMode.SYNC, user_id="u-test")
    return PipelineRuntime(config=cfg, event_sink=CollectorSink())


def _db_sink() -> DatabaseSink:
    """DatabaseSink with a mock DB — we only exercise pure helpers
    (`_phase_index`, `_phase_to_agent`, class-level constants) which
    never touch the database."""
    return DatabaseSink(
        db=MagicMock(),
        tables={
            "generation_jobs": "generation_jobs",
            "generation_job_events": "generation_job_events",
        },
        job_id="j-test",
        user_id="u-test",
        application_id="a-test",
    )


CANONICAL_PHASES = ["recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova"]


# ── Invariant 1: phase order is canonical ─────────────────────────────


def test_phase_order_matches_documented_seven_phase_pipeline() -> None:
    """The frontend progress bar, replay viewer, and SLA reports all
    depend on this exact order. Changing it requires updating every
    consumer in lockstep — these tests will catch a drift."""
    sink = _db_sink()
    assert sink._PHASE_ORDER == CANONICAL_PHASES


def test_phase_order_has_no_duplicates() -> None:
    """A duplicate phase name would make `_phase_index` ambiguous and
    the metrics collector would aggregate two phases under one key."""
    sink = _db_sink()
    assert len(sink._PHASE_ORDER) == len(set(sink._PHASE_ORDER))


def test_phase_step_map_covers_every_canonical_phase() -> None:
    """DatabaseSink._PHASE_STEP drives the completed_steps counter the
    frontend displays. Every canonical phase must have a step number."""
    sink = _db_sink()
    for phase in CANONICAL_PHASES:
        assert phase in sink._PHASE_STEP, f"_PHASE_STEP missing {phase}"


def test_phase_step_total_matches_total_steps_constant() -> None:
    """_TOTAL_STEPS must equal the number of phases or the progress bar
    will never reach 100% (or will reach it early)."""
    sink = _db_sink()
    assert sink._TOTAL_STEPS == len(CANONICAL_PHASES)
    assert sink._TOTAL_STEPS == max(sink._PHASE_STEP.values())


# ── Invariant 1b: _phase_index agrees with _PHASE_ORDER ───────────────


@pytest.mark.parametrize(
    "phase,expected_index",
    list(enumerate(CANONICAL_PHASES)),
    ids=lambda v: str(v),
)
def test_phase_index_returns_position_in_canonical_order(
    phase, expected_index
) -> None:
    """`_phase_index` is consumed by the progress-percent calculation
    on the dashboard. If it disagrees with `_PHASE_ORDER` the bar
    will jump or stall."""
    # parametrize unpacks tuples; we get (index, name) here.
    idx, name = phase, expected_index
    sink = _db_sink()
    assert sink._phase_index(name) == idx


def test_phase_index_returns_minus_one_for_unknown_phase() -> None:
    """Unknown phases must return -1 (not 0, not None, not raise) so
    the progress calculation can detect-and-skip without crashing
    the whole job."""
    sink = _db_sink()
    assert sink._phase_index("not_a_real_phase") == -1
    assert sink._phase_index("") == -1
    assert sink._phase_index("RECON") == -1, "case sensitive on purpose"


# ── Invariant 1c: _phase_to_agent covers every canonical phase ────────


def test_phase_to_agent_maps_every_canonical_phase_to_itself() -> None:
    """Every phase has a same-named agent persona. If a phase loses
    its persona mapping the agent_status SSE event will broadcast
    a generic name instead of the persona, breaking the replay UI."""
    sink = _db_sink()
    for name in CANONICAL_PHASES:
        assert sink._phase_to_agent(name) == name, f"missing persona for {name!r}"


def test_phase_to_agent_handles_initializing_alias() -> None:
    """The 'initializing' phase emits before recon proper and shares
    its persona. Pin that alias."""
    sink = _db_sink()
    assert sink._phase_to_agent("initializing") == "recon"


def test_phase_to_agent_falls_back_to_pipeline_for_empty_or_unknown() -> None:
    """Empty / unknown names must fall back to a non-empty placeholder
    so log lines and SSE payloads are never blank."""
    sink = _db_sink()
    assert sink._phase_to_agent("") == "pipeline"
    assert sink._phase_to_agent("custom_one_off") == "custom_one_off"


# ── Invariant 3: PHASE_SLO_MS budget covers every running phase ───────


def test_phase_slo_ms_has_entry_for_every_canonical_phase() -> None:
    """A missing SLO entry means the slow-phase warning silently never
    fires for that phase — operators lose visibility into regressions."""
    missing = [p for p in CANONICAL_PHASES if p not in PHASE_SLO_MS]
    assert missing == [], (
        f"PHASE_SLO_MS missing budget for: {missing}. "
        "Add an entry whenever you add a new phase."
    )


def test_phase_slo_ms_includes_persist_post_pipeline_step() -> None:
    """`persist` is not a `_PHASE_ORDER` member but runs after nova
    and gets its own SLO. If it disappears the document-library write
    timing falls off the dashboard."""
    assert "persist" in PHASE_SLO_MS
    assert PHASE_SLO_MS["persist"] > 0


def test_all_phase_slo_budgets_are_positive_milliseconds() -> None:
    """A zero or negative budget would make every run trip the slow-
    phase warning, which would be ignored as noise."""
    for phase, budget in PHASE_SLO_MS.items():
        assert isinstance(budget, int), f"{phase} budget is not int"
        assert budget > 0, f"{phase} budget must be > 0, got {budget}"


# ── Invariant 2: phase timing is monotonic & durable ──────────────────


def test_begin_phase_records_start_time_in_internal_state() -> None:
    rt = _runtime()
    assert "recon" not in rt._phase_started_at
    rt._begin_phase("recon")
    assert "recon" in rt._phase_started_at
    assert isinstance(rt._phase_started_at["recon"], float)


def test_finish_phase_writes_duration_to_latencies_map() -> None:
    rt = _runtime()
    rt._begin_phase("atlas")
    time.sleep(0.005)  # 5ms minimum so duration is unambiguously positive
    duration = rt._finish_phase("atlas")
    assert duration >= 0
    assert rt._phase_latencies["atlas"] == duration
    # Started-at entry was popped — preventing accidental double-finish.
    assert "atlas" not in rt._phase_started_at


def test_finish_phase_without_begin_returns_existing_or_zero() -> None:
    """Calling _finish_phase('foo') without first calling _begin_phase
    must return the existing latency (0 if none) WITHOUT writing
    a bogus negative or huge number to the latency map."""
    rt = _runtime()
    out = rt._finish_phase("recon")
    assert out == 0
    assert rt._phase_latencies.get("recon", 0) == 0


def test_finish_phase_idempotent_on_double_call() -> None:
    """Defensive double-finish (e.g. error path AND finally block both
    finishing the same phase) must not corrupt the latency value."""
    rt = _runtime()
    rt._begin_phase("quill")
    time.sleep(0.005)
    first = rt._finish_phase("quill")
    second = rt._finish_phase("quill")  # no _begin_phase between
    assert second == first, "second finish must return the cached value"
    assert rt._phase_latencies["quill"] == first


def test_finish_phase_durations_are_non_negative_for_canonical_phases() -> None:
    """Every canonical phase, when timed, must produce a non-negative
    duration. This guards against the perf_counter() going backwards
    (which would corrupt downstream rollups)."""
    rt = _runtime()
    for phase in CANONICAL_PHASES:
        rt._begin_phase(phase)
        duration = rt._finish_phase(phase)
        assert duration >= 0, f"{phase} produced negative duration {duration}"


def test_phase_latencies_persists_across_multiple_phases() -> None:
    """The whole pipeline must end with one entry per phase that ran,
    so the SSE 'complete' event can broadcast the full breakdown."""
    rt = _runtime()
    for phase in CANONICAL_PHASES:
        rt._begin_phase(phase)
        rt._finish_phase(phase)
    for phase in CANONICAL_PHASES:
        assert phase in rt._phase_latencies, f"{phase} missing from latencies"


# ── SLO threshold semantics ───────────────────────────────────────────


def test_recon_slo_is_under_atlas_slo() -> None:
    """Recon (single LLM intel call) should be cheaper than Atlas
    (resume parse + benchmark build with multiple LLM calls).
    If this inverts, someone has added expensive work to recon —
    the test forces a deliberate budget update rather than silent drift."""
    assert PHASE_SLO_MS["recon"] < PHASE_SLO_MS["atlas"]


def test_quill_has_largest_per_phase_budget() -> None:
    """Quill runs three drafters in parallel (CV + cover + roadmap)
    and is by design the longest phase. If anything else exceeds it,
    that phase has bloated and needs investigation."""
    others = {k: v for k, v in PHASE_SLO_MS.items() if k != "quill"}
    assert all(v <= PHASE_SLO_MS["quill"] for v in others.values()), (
        f"Quill's SLO ({PHASE_SLO_MS['quill']}ms) is no longer the largest. "
        f"Other budgets: {others}"
    )


def test_nova_slo_is_smallest_among_phases() -> None:
    """Nova is the formatting/finalisation step — it does no LLM work
    and must stay cheap. If this fails Nova has acquired LLM work it
    shouldn't have."""
    assert PHASE_SLO_MS["nova"] == min(PHASE_SLO_MS.values())
