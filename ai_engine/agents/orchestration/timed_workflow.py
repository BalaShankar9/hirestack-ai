"""Shared timed workflow scaffold for lightweight agent orchestrators."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar
from uuid import uuid4

from .phase_contract import WorkflowPhaseStatus, get_workflow_phase_order

T = TypeVar("T")


@dataclass
class TimedWorkflow:
    """Capture per-phase timings for small async orchestrators.

    This is intentionally minimal: it standardizes workflow ids, per-phase
    latency measurement, and end-to-end latency without forcing a full event
    bus or durable runtime onto lightweight feature orchestrators.
    """

    workflow_name: str
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    phase_latencies: dict[str, int] = field(default_factory=dict)
    phase_statuses: dict[str, str] = field(default_factory=dict)
    _phase_order: tuple[str, ...] = field(default=(), init=False, repr=False)
    _last_phase_index: int = field(default=-1, init=False, repr=False)
    _started_at: float = field(default_factory=time.perf_counter, init=False, repr=False)

    def __post_init__(self) -> None:
        self._phase_order = get_workflow_phase_order(self.workflow_name)

    def _validate_phase_name(self, phase_name: str) -> None:
        if not self._phase_order:
            return
        if phase_name not in self._phase_order:
            raise ValueError(
                f"Unknown phase {phase_name!r} for workflow {self.workflow_name!r}",
            )
        phase_index = self._phase_order.index(phase_name)
        if phase_name in self.phase_statuses:
            raise ValueError(
                f"Phase {phase_name!r} already executed for workflow {self.workflow_name!r}",
            )
        if phase_index < self._last_phase_index:
            raise ValueError(
                f"Phase {phase_name!r} executed out of order for workflow {self.workflow_name!r}",
            )
        self._last_phase_index = phase_index

    async def run_phase(
        self,
        phase_name: str,
        phase_fn: Callable[[], Awaitable[T]],
    ) -> T:
        self._validate_phase_name(phase_name)
        phase_started = time.perf_counter()
        self.phase_statuses[phase_name] = WorkflowPhaseStatus.RUNNING.value
        try:
            result = await phase_fn()
        except Exception:
            self.phase_statuses[phase_name] = WorkflowPhaseStatus.FAILED.value
            raise
        finally:
            self.phase_latencies[phase_name] = int(
                (time.perf_counter() - phase_started) * 1000,
            )
        self.phase_statuses[phase_name] = WorkflowPhaseStatus.COMPLETED.value
        return result

    @property
    def latency_ms(self) -> int:
        return int((time.perf_counter() - self._started_at) * 1000)