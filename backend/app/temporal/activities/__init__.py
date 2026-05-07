"""Generation workflow activities (PR m6-pr17).

Every activity here is a thin, deterministic-friendly seam over the
existing application layer. The worker registers them; the workflow
calls them through `workflow.execute_activity`. Replacing the default
implementations is how unit tests inject behaviour without monkey-
patching globals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from temporalio import activity


# ── DTOs ───────────────────────────────────────────────────────────────
@dataclass
class GenerationInput:
    job_id: str
    org_id: str
    user_id: str
    document_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationStep:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationPlan:
    steps: list[GenerationStep]


@dataclass
class StepResult:
    step: str
    output: dict[str, Any] = field(default_factory=dict)


@dataclass
class CritiqueResult:
    passed: bool
    score: float = 1.0
    reason: str = ""


@dataclass
class GenerationOutcome:
    job_id: str
    persisted_id: str
    steps: list[StepResult]


# ── pluggable hook bundle ─────────────────────────────────────────────
@dataclass
class ActivityHooks:
    """Default activity behaviour. Tests pass a custom instance to the
    worker; production wires real services."""

    plan: Callable[[GenerationInput], GenerationPlan] = field(
        default=lambda inp: GenerationPlan(
            steps=[GenerationStep(name=f"draft_{inp.document_type}")]
        )
    )
    execute: Callable[[GenerationInput, GenerationStep], StepResult] = field(
        default=lambda inp, step: StepResult(step=step.name, output={"ok": True})
    )
    critique: Callable[[GenerationInput, StepResult], CritiqueResult] = field(
        default=lambda inp, res: CritiqueResult(passed=True, score=1.0)
    )
    persist: Callable[[GenerationInput, list[StepResult]], str] = field(
        default=lambda inp, results: f"doc_{inp.job_id}"
    )
    emit_event: Callable[[GenerationOutcome], None] = field(default=lambda outcome: None)


# ── activity definitions ──────────────────────────────────────────────
def build_activities(hooks: Optional[ActivityHooks] = None) -> list[Callable[..., Any]]:
    """Return a fresh list of activity callables bound to ``hooks``.

    Activities are defined inside a closure so each test gets its own
    isolated set without global state. Temporal cares about the
    ``__name__`` attribute, which `@activity.defn(name=...)` overrides.
    """
    h = hooks or ActivityHooks()

    @activity.defn(name="plan")
    async def plan(inp: GenerationInput) -> GenerationPlan:
        return h.plan(inp)

    @activity.defn(name="execute_step")
    async def execute_step(inp: GenerationInput, step: GenerationStep) -> StepResult:
        return h.execute(inp, step)

    @activity.defn(name="critique")
    async def critique(inp: GenerationInput, result: StepResult) -> CritiqueResult:
        return h.critique(inp, result)

    @activity.defn(name="persist")
    async def persist(inp: GenerationInput, results: list[StepResult]) -> str:
        return h.persist(inp, results)

    @activity.defn(name="emit_event")
    async def emit_event(outcome: GenerationOutcome) -> None:
        h.emit_event(outcome)

    return [plan, execute_step, critique, persist, emit_event]


__all__ = [
    "ActivityHooks",
    "CritiqueResult",
    "GenerationInput",
    "GenerationOutcome",
    "GenerationPlan",
    "GenerationStep",
    "StepResult",
    "build_activities",
]
