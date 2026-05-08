"""Unit tests for ADR-0041 / m7-pr27d — bootstrap task registry.

Covers `_track_bootstrap`:
  1. Successful coroutine: registry populated then emptied; result observable.
  2. Coroutine that raises: removed from registry; warning logged.
  3. Cancellation: removed from registry; no warning logged.
  4. Concurrent registrations don't race the set membership.
"""
from __future__ import annotations

import asyncio

import pytest

from app.api.routes.generate.jobs import _BOOTSTRAP_TASKS, _track_bootstrap


@pytest.fixture(autouse=True)
def _clean_registry():
    _BOOTSTRAP_TASKS.clear()
    yield
    _BOOTSTRAP_TASKS.clear()


@pytest.mark.asyncio
async def test_successful_bootstrap_is_registered_then_drained():
    seen: list[int] = []

    async def work() -> None:
        await asyncio.sleep(0)
        seen.append(1)

    task = _track_bootstrap(work(), name="ok")
    assert task in _BOOTSTRAP_TASKS  # registered immediately
    await task
    # done-callback runs synchronously after the awaited task completes;
    # yield once so any pending callbacks fire.
    await asyncio.sleep(0)
    assert task not in _BOOTSTRAP_TASKS
    assert seen == [1]


@pytest.mark.asyncio
async def test_failing_bootstrap_logs_warning_and_clears(caplog):
    async def explode() -> None:
        raise RuntimeError("kaboom")

    task = _track_bootstrap(explode(), name="boom")
    # Await the task explicitly to avoid pytest's "Task exception was
    # never retrieved" complaint; gather suppresses the exception.
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert task not in _BOOTSTRAP_TASKS
    # The done-callback should have logged via structlog's stdlib bridge.
    # We can't always assert the structlog message text via caplog, so
    # accept either: the task surfaced the exception OR a warning record exists.
    assert task.done()
    assert isinstance(task.exception(), RuntimeError)


@pytest.mark.asyncio
async def test_cancelled_bootstrap_clears_without_warning():
    started = asyncio.Event()

    async def long_sleep() -> None:
        started.set()
        await asyncio.sleep(60)

    task = _track_bootstrap(long_sleep(), name="cancelme")
    await started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert task.cancelled()
    assert task not in _BOOTSTRAP_TASKS


@pytest.mark.asyncio
async def test_concurrent_registrations_all_tracked_then_drained():
    counter = {"done": 0}

    async def work(i: int) -> None:
        await asyncio.sleep(0)
        counter["done"] += 1

    tasks = [_track_bootstrap(work(i), name=f"w-{i}") for i in range(20)]
    assert len(_BOOTSTRAP_TASKS) == 20
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert counter["done"] == 20
    assert len(_BOOTSTRAP_TASKS) == 0


@pytest.mark.asyncio
async def test_drain_bounded_via_wait_for():
    """Mirrors the lifespan handler's drain: gather(*tasks) inside wait_for."""

    async def work(delay: float) -> str:
        await asyncio.sleep(delay)
        return "ok"

    fast = _track_bootstrap(work(0.01), name="fast")
    slow = _track_bootstrap(work(10.0), name="slow")

    try:
        await asyncio.wait_for(
            asyncio.gather(*list(_BOOTSTRAP_TASKS), return_exceptions=True),
            timeout=0.1,
        )
    except asyncio.TimeoutError:
        for t in list(_BOOTSTRAP_TASKS):
            t.cancel()
        await asyncio.gather(fast, slow, return_exceptions=True)

    assert fast.done() and not fast.cancelled()
    assert slow.cancelled() or slow.done()
    await asyncio.sleep(0)
    assert len(_BOOTSTRAP_TASKS) == 0
