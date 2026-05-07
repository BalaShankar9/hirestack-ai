"""Generation workflow (PR m6-pr17).

`GenerationWorkflow.run` orchestrates: plan → for each step (execute →
critique with retry ≤3) → persist → emit_event. Determinism is
preserved: no random, no time, no I/O outside `workflow.execute_activity`.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        CritiqueResult,
        GenerationInput,
        GenerationOutcome,
        GenerationPlan,
        GenerationStep,
        StepResult,
    )


CRITIC_MAX_ATTEMPTS = 3


class CriticGaveUp(ApplicationError):
    """Raised inside the workflow when the critic loop exhausts retries.

    Subclasses ``ApplicationError`` so the message round-trips cleanly
    through Temporal's failure conversion (it lands on the client as the
    `cause` of a ``WorkflowFailureError``)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, type="CriticGaveUp", non_retryable=True)


@workflow.defn(name="GenerationWorkflow")
class GenerationWorkflow:
    @workflow.run
    async def run(self, inp: GenerationInput) -> GenerationOutcome:
        plan: GenerationPlan = await workflow.execute_activity(
            "plan",
            inp,
            result_type=GenerationPlan,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        results: list[StepResult] = []
        for step in plan.steps:
            results.append(await self._run_step(inp, step))

        persisted_id: str = await workflow.execute_activity(
            "persist",
            args=[inp, results],
            result_type=str,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        outcome = GenerationOutcome(
            job_id=inp.job_id, persisted_id=persisted_id, steps=results
        )
        await workflow.execute_activity(
            "emit_event",
            outcome,
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        return outcome

    async def _run_step(self, inp: GenerationInput, step: GenerationStep) -> StepResult:
        last_reason = ""
        for attempt in range(1, CRITIC_MAX_ATTEMPTS + 1):
            result: StepResult = await workflow.execute_activity(
                "execute_step",
                args=[inp, step],
                result_type=StepResult,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            verdict: CritiqueResult = await workflow.execute_activity(
                "critique",
                args=[inp, result],
                result_type=CritiqueResult,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            if verdict.passed:
                return result
            last_reason = verdict.reason or "critic_failed"
            workflow.logger.warning(
                "critic_failed step=%s attempt=%d reason=%s",
                step.name, attempt, last_reason,
            )
        raise CriticGaveUp(f"step={step.name} reason={last_reason}")
