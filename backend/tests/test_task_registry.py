"""m11-pr43: TaskRegistry — generic fire-and-forget asyncio bookkeeping."""
from __future__ import annotations

import asyncio

import pytest

from app.core.task_registry import (
    TaskRegistry,
    bootstrap_registry,
    scheduler_registry,
)


@pytest.fixture
def reg() -> TaskRegistry:
    return TaskRegistry(name="test")


@pytest.mark.asyncio
async def test_spawn_tracks_then_releases_on_completion(reg: TaskRegistry):
    async def _ok():
        await asyncio.sleep(0)

    t = reg.spawn(_ok(), name="ok-1")
    assert reg.inflight() == 1
    assert t in reg
    await t
    # done-callback runs synchronously after the task completes — yield once.
    await asyncio.sleep(0)
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_spawn_failure_invokes_failure_hook(reg):
    seen: list[tuple[str, str, str]] = []

    def hook(registry: str, task_name: str, exc: BaseException) -> None:
        seen.append((registry, task_name, type(exc).__name__))

    reg = TaskRegistry(name="hooked", failure_hook=hook)

    async def _boom():
        raise RuntimeError("nope")

    t = reg.spawn(_boom(), name="b-1")
    with pytest.raises(RuntimeError):
        await t
    await asyncio.sleep(0)
    assert seen == [("hooked", "b-1", "RuntimeError")]
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_failure_hook_exception_does_not_break_accounting():
    def evil_hook(*_a, **_kw):
        raise ValueError("hook crash")

    reg = TaskRegistry(name="evil", failure_hook=evil_hook)

    async def _boom():
        raise RuntimeError("x")

    t = reg.spawn(_boom(), name="b")
    with pytest.raises(RuntimeError):
        await t
    await asyncio.sleep(0)
    # Even though the hook raised, the registry still released the task.
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_cancelled_task_does_not_invoke_failure_hook():
    seen: list = []
    reg = TaskRegistry(name="r", failure_hook=lambda *a: seen.append(a))

    async def _slow():
        await asyncio.sleep(10)

    t = reg.spawn(_slow(), name="slow")
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    await asyncio.sleep(0)
    assert seen == []
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_adopt_existing_task(reg: TaskRegistry):
    async def _ok():
        await asyncio.sleep(0)

    task = asyncio.create_task(_ok(), name="adopted")
    reg.adopt(task)
    assert reg.inflight() == 1
    await task
    await asyncio.sleep(0)
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_drain_completes_running_tasks_within_timeout(reg: TaskRegistry):
    finished: list[str] = []

    async def _slow(name: str):
        await asyncio.sleep(0.01)
        finished.append(name)

    reg.spawn(_slow("a"), name="a")
    reg.spawn(_slow("b"), name="b")
    await reg.drain(timeout=2.0)
    assert sorted(finished) == ["a", "b"]
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_drain_cancels_on_timeout(reg: TaskRegistry):
    async def _hang():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    reg.spawn(_hang(), name="hang")
    await reg.drain(timeout=0.05)
    # After drain timeout, the task should be cancelled and removed.
    assert reg.inflight() == 0


@pytest.mark.asyncio
async def test_drain_on_empty_registry_is_noop(reg: TaskRegistry):
    # Should not raise or hang even with nothing to drain.
    await reg.drain(timeout=0.01)
    assert reg.inflight() == 0


def test_default_singletons_exist_and_are_distinct():
    assert isinstance(bootstrap_registry, TaskRegistry)
    assert isinstance(scheduler_registry, TaskRegistry)
    assert bootstrap_registry is not scheduler_registry
    assert bootstrap_registry.name == "bootstrap"
    assert scheduler_registry.name == "scheduler"


def test_bootstrap_alias_in_jobs_module_is_same_object():
    """Backwards-compat: ``_BOOTSTRAP_TASKS`` in jobs.py must alias the
    bootstrap_registry's internal set so /metrics + lifespan drain work."""
    from app.api.routes.generate.jobs import _BOOTSTRAP_TASKS
    assert _BOOTSTRAP_TASKS is bootstrap_registry._tasks


@pytest.mark.asyncio
async def test_bootstrap_failure_hook_increments_queue_metrics():
    """Lazy import path: failure hook must call queue_metrics.inc_bootstrap_failure."""
    from app.core import queue_metrics as qm

    qm.reset_for_tests()
    try:

        async def _boom():
            raise RuntimeError("x")

        t = bootstrap_registry.spawn(_boom(), name="gen-bootstrap-test:abc-1")
        with pytest.raises(RuntimeError):
            await t
        await asyncio.sleep(0)
        snap = qm.snapshot()
        # ``inc_bootstrap_failure`` strips the ``:<id>`` suffix.
        assert snap["bootstrap_task_failures_total"].get("gen-bootstrap-test") == 1
    finally:
        qm.reset_for_tests()
        bootstrap_registry.reset_for_tests()
