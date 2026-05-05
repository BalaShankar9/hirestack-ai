"""AIM Quality Gate.

Single source of truth for the show / regen / flag decision given a reviewer
verdict (or a manual draft score). Mirrors the thresholds defined in
``ai_engine.agents.aim.reviewer`` and centralises the rule referenced in the
plan: *outputs scoring < 85 are stored as non-current versions and never
rendered as primary content unless the user explicitly overrides*.

The gate is intentionally framework-free (pure functions over dicts/floats) so
it can be reused from services, route handlers, evals, and tests without
pulling in agent or DB dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from ai_engine.agents.aim.reviewer import (
    GREY_ZONE,
    PASS_THRESHOLD,
    REVISION_THRESHOLD,
)

__all__ = [
    "GateAction",
    "GateDecision",
    "decide",
    "decide_from_attempt",
    "PASS_THRESHOLD",
    "REVISION_THRESHOLD",
    "GREY_ZONE",
]


class GateAction(str, Enum):
    SHOW = "show"          # score ≥ PASS_THRESHOLD and all dims pass → surface as current
    REGEN = "regen"        # score in [REVISION_THRESHOLD, PASS_THRESHOLD) → another attempt is worth it
    FLAG = "flag"          # score < REVISION_THRESHOLD → store but mark as low-quality
    OVERRIDE = "override"  # caller asked us to surface anyway (e.g. ?force=true)


@dataclass(frozen=True)
class GateDecision:
    action: GateAction
    is_current: bool       # whether this attempt should become the current version
    passed_gate: bool      # mirrors the boolean stored on the row
    in_grey_zone: bool     # 70–85 — reviewer should escalate to Pro on next attempt
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "is_current": self.is_current,
            "passed_gate": self.passed_gate,
            "in_grey_zone": self.in_grey_zone,
            "reason": self.reason,
        }


def decide(
    weighted_score: float,
    sub_scores: Optional[Mapping[str, float]] = None,
    *,
    force: bool = False,
) -> GateDecision:
    """Decide what to do with a single reviewer-scored attempt.

    Args:
        weighted_score: Reviewer's weighted 0–100 score.
        sub_scores: Per-dimension scores. If provided, ALL dims must be
            ≥ PASS_THRESHOLD for the gate to pass even when ``weighted_score``
            clears it (matches ``AIMReviewerAgent`` semantics).
        force: Caller override (``?force=true``) — surfaces the attempt as
            current regardless of score. Returns ``GateAction.OVERRIDE``.
    """
    score = float(weighted_score or 0.0)
    in_grey = GREY_ZONE[0] <= score < GREY_ZONE[1]

    if force:
        return GateDecision(
            action=GateAction.OVERRIDE,
            is_current=True,
            passed_gate=False,
            in_grey_zone=in_grey,
            reason=f"force override (score={score:.1f})",
        )

    all_dims_pass = True
    if sub_scores:
        all_dims_pass = all(
            float(sub_scores.get(k, 0) or 0) >= PASS_THRESHOLD
            for k in ("directive_alignment", "analytical_depth",
                      "academic_tone", "originality", "structure")
        )

    if score >= PASS_THRESHOLD and all_dims_pass:
        return GateDecision(
            action=GateAction.SHOW,
            is_current=True,
            passed_gate=True,
            in_grey_zone=False,
            reason=f"passed (score={score:.1f}, all dims ≥ {PASS_THRESHOLD})",
        )

    if score >= REVISION_THRESHOLD:
        return GateDecision(
            action=GateAction.REGEN,
            is_current=False,
            passed_gate=False,
            in_grey_zone=in_grey,
            reason=(
                f"below pass (score={score:.1f}); "
                f"{'grey-zone — escalate to Pro' if in_grey else 'regen recommended'}"
            ),
        )

    return GateDecision(
        action=GateAction.FLAG,
        is_current=False,
        passed_gate=False,
        in_grey_zone=False,
        reason=f"low quality (score={score:.1f} < {REVISION_THRESHOLD}) — flagged",
    )


def decide_from_attempt(
    attempt: Any,
    *,
    force: bool = False,
) -> GateDecision:
    """Convenience wrapper for ``SectionAttempt`` (or any object with
    ``weighted_score`` and ``reviewer.sub_scores``)."""
    sub = None
    reviewer = getattr(attempt, "reviewer", None) or {}
    if isinstance(reviewer, Mapping):
        sub = reviewer.get("sub_scores")
    return decide(
        weighted_score=getattr(attempt, "weighted_score", 0.0),
        sub_scores=sub,
        force=force,
    )
