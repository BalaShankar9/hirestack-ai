"""AIM Quality Gate — unit + anti-low-quality regression tests."""
from __future__ import annotations

import pytest

from app.services.aim.quality_gate import (
    GREY_ZONE,
    PASS_THRESHOLD,
    REVISION_THRESHOLD,
    GateAction,
    decide,
    decide_from_attempt,
)


# ── Core gate logic ────────────────────────────────────────────────


def test_decide_show_when_score_and_all_dims_pass():
    sub = {k: 86 for k in (
        "directive_alignment", "analytical_depth",
        "academic_tone", "originality", "structure",
    )}
    d = decide(weighted_score=88.0, sub_scores=sub)
    assert d.action is GateAction.SHOW
    assert d.is_current is True
    assert d.passed_gate is True
    assert d.in_grey_zone is False


def test_decide_regen_when_in_grey_zone():
    d = decide(weighted_score=80.0)
    assert d.action is GateAction.REGEN
    assert d.is_current is False
    assert d.passed_gate is False
    assert d.in_grey_zone is True


def test_decide_regen_when_just_above_revision_threshold():
    d = decide(weighted_score=REVISION_THRESHOLD)
    assert d.action is GateAction.REGEN
    # 75 falls inside GREY_ZONE (70, 85) so escalation flag is set.
    assert d.in_grey_zone is True


def test_decide_flag_when_below_revision_threshold():
    d = decide(weighted_score=60.0)
    assert d.action is GateAction.FLAG
    assert d.is_current is False
    assert d.passed_gate is False


def test_decide_force_override_surfaces_low_score_as_current():
    d = decide(weighted_score=42.0, force=True)
    assert d.action is GateAction.OVERRIDE
    assert d.is_current is True
    assert d.passed_gate is False
    assert "force" in d.reason


def test_decide_score_passes_but_one_dim_fails_does_not_show():
    sub = {
        "directive_alignment": 90,
        "analytical_depth": 90,
        "academic_tone": 90,
        "originality": 70,  # below PASS_THRESHOLD
        "structure": 90,
    }
    d = decide(weighted_score=86.0, sub_scores=sub)
    # weighted clears 85 but originality fails → must NOT be SHOW
    assert d.action is not GateAction.SHOW
    assert d.passed_gate is False


def test_decide_from_attempt_uses_sub_scores_from_reviewer():
    class _A:
        weighted_score = 90.0
        reviewer = {"sub_scores": {k: 90 for k in (
            "directive_alignment", "analytical_depth",
            "academic_tone", "originality", "structure",
        )}}
    d = decide_from_attempt(_A())
    assert d.action is GateAction.SHOW


# ── Anti-low-quality regression: 10 known-bad samples must all FLAG/REGEN ──

# Each entry simulates a reviewer verdict for a known-bad attempt.
# The plan requires: all 10 must score < REVISION_THRESHOLD (75) and the gate
# must NOT mark them as current.
_BAD_SAMPLES = [
    # (description, weighted, sub_scores)
    ("listicle no analysis", 42.0, dict(directive_alignment=30, analytical_depth=20,
                                          academic_tone=60, originality=50, structure=50)),
    ("banned-phrase soup", 38.0, dict(directive_alignment=40, analytical_depth=20,
                                       academic_tone=30, originality=40, structure=60)),
    ("surface summary", 55.0, dict(directive_alignment=55, analytical_depth=30,
                                    academic_tone=70, originality=45, structure=70)),
    ("repetitive shingles", 49.0, dict(directive_alignment=50, analytical_depth=40,
                                        academic_tone=55, originality=20, structure=60)),
    ("off-directive", 33.0, dict(directive_alignment=10, analytical_depth=40,
                                   academic_tone=60, originality=50, structure=50)),
    ("no critique markers", 60.0, dict(directive_alignment=60, analytical_depth=50,
                                        academic_tone=70, originality=55, structure=60)),
    ("informal voice", 51.0, dict(directive_alignment=55, analytical_depth=45,
                                   academic_tone=30, originality=60, structure=65)),
    ("plagiarism-like cliches", 44.0, dict(directive_alignment=50, analytical_depth=30,
                                            academic_tone=55, originality=10, structure=65)),
    ("incoherent structure", 47.0, dict(directive_alignment=55, analytical_depth=45,
                                         academic_tone=60, originality=50, structure=20)),
    ("everything mid-low", 58.0, dict(directive_alignment=60, analytical_depth=55,
                                        academic_tone=60, originality=58, structure=55)),
]


@pytest.mark.parametrize("desc,score,sub", _BAD_SAMPLES)
def test_anti_low_quality_regression_all_flagged(desc, score, sub):
    d = decide(weighted_score=score, sub_scores=sub)
    assert d.is_current is False, f"{desc!r} must not be marked current"
    assert d.passed_gate is False, f"{desc!r} must not pass gate"
    assert d.action in (GateAction.FLAG, GateAction.REGEN), (
        f"{desc!r} expected FLAG/REGEN, got {d.action}"
    )
    # Plan says known-bad outputs must score < 75 (REVISION_THRESHOLD).
    assert score < REVISION_THRESHOLD, (
        f"sample {desc!r} weight={score} is not < {REVISION_THRESHOLD} — "
        "tighten the sample"
    )
