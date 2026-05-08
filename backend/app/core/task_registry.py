"""
Generic registry for fire-and-forget asyncio tasks.

ADR-0041 introduced a hand-rolled registry for the generation bootstrap
coroutines (`backend/app/api/routes/generate/jobs.py::_BOOTSTRAP_TASKS`).
The same pattern recurred for `JobWatchdog`, the periodic stale-job
cleanup loop, and (eventually) the scheduler-process bootstrap. m11-pr43
extracts it so we have ONE place to:

  * hold strong references (prevent the loop GC'ing the task mid-flight);
  * surface failures via a structured done-callback + metrics hook;
  * drain on SIGTERM with a bounded gather-then-cancel.

This module deliberately depends on nothing inside `app.*` so it can be
imported from any layer (worker process, scheduler process, FastAPI
lifespan) without circular-import pain.

USAGE (spawn pattern — for short-lived dispatch coroutines):

    from app.core.task_registry import TaskRegistry, bootstrap_registry

    bootstrap_registry.spawn(my_coro(), name="gen-bootstrap-enqueue:abc")

USAGE (adopt pattern — for long-lived workers that build their own task):

    task = asyncio.create_task(self._run(), name="job-watchdog")
    registry.adopt(task)

USAGE (shutdown drain — call from FastAPI lifespan):

    await registry.drain(timeout=5.0)

The default `bootstrap_registry` singleton is what the generation
dispatch path uses. Other subsystems (scheduler bootstrap, watchdogs)
should construct their own named registry so drain order and timeouts
can be tuned independently.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Iterator, Optional

import structlog

logger = structlog.get_logger(__name__)


# Optional metrics hook signature: (registry_name, task_name, exception) -> None.
# Kept as a plain callable rather than a hard import on `app.core.queue_metrics`
# to keep this module dependency-free and exception-safe.
FailureHook = Callable[[str, str, BaseException], None]


class TaskRegistry:
    """Track fire-and-forget asyncio tasks for safe lifetime management."""

    __slots__ = ("_name", "_tasks", "_failure_hook")

    def __init__(
        self,
        name: str = "default",
        *,
        failure_hook: Optional[FailureHook] = None,
    ) -> None:
        self._name = name
        self._tasks: "set[asyncio.Task[Any]]" = set()
        self._failure_hook = failure_hook

    # ── introspection ────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    def __len__(self) -> int:
        return len(self._tasks)

    def __iter__(self) -> Iterator["asyncio.Task[Any]"]:
        return iter(self._tasks)

    def inflight(self) -> int:
        return len(self._tasks)

    # ── registration ─────────────────────────────────────────────────

    def spawn(
        self,
        coro: Awaitable[Any],
        *,
        name: str,
    ) -> "asyncio.Task[Any]":
        """Create + track a new task. Use for short-lived dispatch coroutines."""
        task = asyncio.create_task(coro, name=name)
        self._register(task, name)
        return task

    def adopt(self, task: "asyncio.Task[Any]") -> "asyncio.Task[Any]":
        """Track an externally-created task. Use for long-running workers
        that build their own task (e.g. ``JobWatchdog.start``)."""
        name = task.get_name() or f"<{self._name}-anon>"
        self._register(task, name)
        return task

    def _register(self, task: "asyncio.Task[Any]", name: str) -> None:
        self._tasks.add(task)
        task.add_done_callback(lambda t, n=name: self._on_done(t, n))

    def _on_done(self, task: "asyncio.Task[Any]", name: str) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return
        # Failure: surface via metrics hook (if any) and a structured warn log.
        if self._failure_hook is not None:
            try:
                self._failure_hook(self._name, name, exc)
            except Exception:
                # An observability hook MUST NEVER break task accounting.
                pass
        try:
            logger.warning(
                "task_registry.task_failed",
                registry=self._name,
                task=name,
                error=str(exc)[:300],
            )
        except Exception:
            pass

    # ── shutdown ─────────────────────────────────────────────────────

    async def drain(self, *, timeout: float = 5.0) -> None:
        """Wait up to ``timeout`` seconds for in-flight tasks, then cancel."""
        if not self._tasks:
            return
        pending = list(self._tasks)
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                logger.warning(
                    "task_registry.drain_timeout",
                    registry=self._name,
                    remaining=len(self._tasks),
                )
            except Exception:
                pass
            for t in list(self._tasks):
                t.cancel()
            # Best-effort wait for cancellation to settle.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(self._tasks), return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                pass

    # ── tests ────────────────────────────────────────────────────────

    def reset_for_tests(self) -> None:
        """Drop tracked references without cancelling. Tests only."""
        self._tasks.clear()


# ── default registries ──────────────────────────────────────────────────

def _bootstrap_failure_hook(_registry: str, task_name: str, _exc: BaseException) -> None:
    """Wire bootstrap failures into queue_metrics. Lazy-imported to avoid
    a circular dependency at module load."""
    try:
        from app.core import queue_metrics as _qm
        _qm.inc_bootstrap_failure(task_name)
    except Exception:
        pass


# Singleton consumed by the generation dispatch path. Replaces the
# module-level ``_BOOTSTRAP_TASKS`` set + ad-hoc ``_track_bootstrap``
# in ``backend/app/api/routes/generate/jobs.py``.
bootstrap_registry: TaskRegistry = TaskRegistry(
    name="bootstrap",
    failure_hook=_bootstrap_failure_hook,
)


# Used by the FastAPI lifespan to track scheduler-side fire-and-forget
# tasks (periodic stale-job cleanup, JobWatchdog). Drained separately
# from ``bootstrap_registry`` because its tasks are long-running and
# require a CANCEL-then-await rather than a wait-for-completion drain.
scheduler_registry: TaskRegistry = TaskRegistry(
    name="scheduler",
    failure_hook=_bootstrap_failure_hook,
)
