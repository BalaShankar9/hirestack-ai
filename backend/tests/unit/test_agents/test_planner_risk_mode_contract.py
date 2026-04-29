"""Contract pin for the planner risk-mode taxonomy.

ADR-0015 ratifies `conservative | normal | aggressive` as the
permanent enum (not the brief's `fast | balanced | strict |
evidence_first`). This test fails loudly if either the value set or
the score-threshold mapping changes without a corresponding ADR
update.

See: docs/adrs/0015-planner-risk-mode-and-strategy-memory.md
"""
from __future__ import annotations

import pytest

from ai_engine.agents.planner import PipelinePlan, PlanArtifact, PlannerAgent


RATIFIED_RISK_MODES = {"conservative", "normal", "aggressive"}


@pytest.mark.parametrize(
    "jd,profile,evidence,expected",
    [
        (0, 0, 0, "conservative"),
        (30, 30, 30, "conservative"),
        (39, 39, 39, "conservative"),
        (40, 40, 40, "normal"),
        (50, 50, 50, "normal"),
        (69, 69, 69, "normal"),
        (70, 70, 70, "aggressive"),
        (100, 100, 100, "aggressive"),
        # Asymmetric: only the average matters.
        (90, 90, 0, "normal"),  # avg = 60
        (100, 100, 100, "aggressive"),
        (0, 100, 50, "normal"),  # avg = 50
    ],
)
def test_determine_risk_mode_thresholds(jd, profile, evidence, expected):
    assert PlannerAgent.determine_risk_mode(jd, profile, evidence) == expected


def test_risk_mode_value_set_is_locked():
    """If this fails, update ADR-0015 before adding/removing a value."""
    seen = set()
    # Sweep the full input space at low resolution; every observed value
    # must be in the ratified set.
    for jd in range(0, 101, 10):
        for profile in range(0, 101, 10):
            for evidence in range(0, 101, 10):
                mode = PlannerAgent.determine_risk_mode(jd, profile, evidence)
                seen.add(mode)
    assert seen.issubset(RATIFIED_RISK_MODES), (
        f"Planner emitted unratified risk_mode(s): {seen - RATIFIED_RISK_MODES}. "
        "Update docs/adrs/0015-planner-risk-mode-and-strategy-memory.md first."
    )
    # All three must be reachable across the sweep — guards against a
    # future regression that silently collapses the enum.
    assert seen == RATIFIED_RISK_MODES


def test_plan_artifact_round_trips_risk_mode():
    plan = PipelinePlan(steps=[], reasoning="test", estimated_latency_hint="fast")
    for mode in RATIFIED_RISK_MODES:
        artifact = PlanArtifact(
            plan=plan,
            jd_quality_score=50,
            profile_quality_score=50,
            evidence_strength_score=50,
            risk_mode=mode,
        )
        assert artifact.to_dict()["risk_mode"] == mode
