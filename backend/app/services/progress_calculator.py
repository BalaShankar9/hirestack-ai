"""
ProgressCalculator — truthful 0..100 progress derived from a BuildPlan.

Replaces the timer-/phase-index-based estimates that the legacy
runtime emits. Progress is `Σ(stage.weight × stage.completion) / total_weight`
where stage.completion is in {0.0, partial, 1.0} and only counts toward
"completed" when the stage's Critic gate has passed.

Usage:
    calc = ProgressCalculator(plan)
    calc.mark_started("atlas.benchmark")
    calc.mark_completed("atlas.benchmark", validated=True)
    pct = calc.percent()                  # → 0..100 int
    phase = calc.current_phase()          # → "atlas"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ai_engine.agents.artifact_contracts import BuildPlan, StagePlan


@dataclass
class _StageState:
    stage: StagePlan
    started: bool = False
    completed: bool = False
    validated: bool = False
    skipped: bool = False
    partial: float = 0.0  # 0..1 progress within this stage when running

    @property
    def completion(self) -> float:
        if self.skipped:
            return 1.0
        if self.completed:
            # Only count fully toward total if validated (or explicitly optional).
            return 1.0 if (self.validated or self.stage.optional) else 0.85
        if self.started:
            return max(0.0, min(0.85, self.partial))  # cap at 85% until done
        return 0.0


@dataclass
class ProgressCalculator:
    plan: BuildPlan
    _stages: Dict[str, _StageState] = field(default_factory=dict, init=False)
    _last_phase: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._stages = {
            s.stage_id: _StageState(stage=s) for s in (self.plan.stages or [])
        }

    # ── mutation ─────────────────────────────────────────────────────

    def mark_started(self, stage_id: str) -> None:
        st = self._stages.get(stage_id)
        if st:
            st.started = True
            self._last_phase = self._phase_of(st.stage)

    def mark_partial(self, stage_id: str, fraction: float) -> None:
        st = self._stages.get(stage_id)
        if st:
            st.started = True
            st.partial = max(0.0, min(1.0, fraction))

    def mark_completed(self, stage_id: str, *, validated: bool = False) -> None:
        st = self._stages.get(stage_id)
        if st:
            st.started = True
            st.completed = True
            st.validated = validated
            st.partial = 1.0
            self._last_phase = self._phase_of(st.stage)

    def mark_skipped(self, stage_id: str) -> None:
        st = self._stages.get(stage_id)
        if st:
            st.skipped = True
            self._last_phase = self._phase_of(st.stage)

    # ── derived state ────────────────────────────────────────────────

    def percent(self) -> int:
        total_weight = self.plan.total_weight()
        if total_weight <= 0:
            return 0
        progress_weight = sum(
            st.stage.weight * st.completion for st in self._stages.values()
        )
        pct = (progress_weight / total_weight) * 100.0
        return max(0, min(100, int(round(pct))))

    def current_phase(self) -> str:
        if self._last_phase:
            return self._last_phase
        # Fallback: first stage that's started or, if none, first stage's phase.
        for st in self._stages.values():
            if st.started:
                return self._phase_of(st.stage)
        if self._stages:
            return self._phase_of(next(iter(self._stages.values())).stage)
        return ""

    def completed_stages(self) -> List[str]:
        return [sid for sid, st in self._stages.items() if st.completed or st.skipped]

    def remaining_stages(self) -> List[str]:
        return [sid for sid, st in self._stages.items() if not (st.completed or st.skipped)]

    def is_complete(self) -> bool:
        return all(st.completed or st.skipped for st in self._stages.values())

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _phase_of(stage: StagePlan) -> str:
        # stage_id format is "<phase>.<thing>"
        return stage.stage_id.split(".", 1)[0] if stage.stage_id else stage.agent_name


def percent_for_plan(
    plan: BuildPlan,
    *,
    completed_stage_ids: Optional[List[str]] = None,
) -> int:
    """One-shot convenience: progress for a plan with the given stages completed."""
    calc = ProgressCalculator(plan=plan)
    for sid in completed_stage_ids or []:
        calc.mark_completed(sid, validated=True)
    return calc.percent()
