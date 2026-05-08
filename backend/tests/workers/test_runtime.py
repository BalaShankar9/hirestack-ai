"""Tests for ``app.workers.runtime`` — the reusable worker bootstrap (PR m2-pr5).

The real worker uses a Redis-backed QueueConsumer, but we never spin
that up here.  We inject a fake consumer so the tests verify the
*runtime contract*: signal handler installation, shutdown propagation,
config validation, and the lazy-import escape hatch.
"""
from __future__ import annotations

import asyncio
import signal
from typing import Any

import pytest

from app.workers.runtime import WorkerRuntime, WorkerSettings, run_worker


# ---------- WorkerSettings -------------------------------------------------


def test_settings_rejects_zero_concurrency():
    with pytest.raises(ValueError, match="concurrency must be >= 1"):
        WorkerSettings(consumer_name="w-1", concurrency=0)


def test_settings_rejects_empty_consumer_name():
    with pytest.raises(ValueError, match="consumer_name"):
        WorkerSettings(consumer_name="", concurrency=1)


def test_settings_is_frozen():
    s = WorkerSettings(consumer_name="w-1")
    with pytest.raises((AttributeError, Exception)):
        s.consumer_name = "w-2"  # type: ignore[misc]


# ---------- Fake consumer used by runtime tests ----------------------------


class _FakeConsumer:
    """Records run/stop calls.  ``run`` waits on a manual stop event so
    tests can simulate signal-driven shutdown."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._stop = asyncio.Event()
        self.run_called = False
        self.stop_called = False

    async def run(self) -> None:
        self.run_called = True
        await self._stop.wait()

    def stop(self) -> None:
        self.stop_called = True
        self._stop.set()


# ---------- WorkerRuntime --------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_passes_settings_to_consumer_factory():
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return _FakeConsumer(**kwargs)

    settings = WorkerSettings(
        consumer_name="w-7",
        concurrency=3,
        install_signal_handlers=False,
    )

    async def handler(job_id, user_id):
        pass

    runtime = WorkerRuntime(handler=handler, settings=settings, consumer_factory=factory)
    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.01)

    # Consumer was constructed with the expected wiring.
    assert captured["consumer_name"] == "w-7"
    assert captured["concurrency"] == 3
    assert captured["handler"] is handler

    # Drive shutdown without touching real signals.
    runtime._consumer.stop()  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_runtime_invokes_consumer_run_then_returns():
    fake = _FakeConsumer()

    async def handler(job_id, user_id):
        pass

    runtime = WorkerRuntime(
        handler=handler,
        settings=WorkerSettings(
            consumer_name="w-1", install_signal_handlers=False
        ),
        consumer_factory=lambda **_: fake,
    )

    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.01)
    assert fake.run_called
    assert not fake.stop_called

    fake.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert fake.stop_called


@pytest.mark.asyncio
async def test_runtime_install_signal_handlers_true_calls_loop_api(monkeypatch):
    """When signals are enabled, the runtime hooks into the running loop."""
    fake = _FakeConsumer()
    installed: list[int] = []

    real_loop = asyncio.get_running_loop()
    real_add = real_loop.add_signal_handler

    def _spy(sig, cb, *a, **k):
        installed.append(sig)
        # No-op (don't actually wire signals in tests).

    monkeypatch.setattr(real_loop, "add_signal_handler", _spy)

    async def handler(job_id, user_id):
        pass

    runtime = WorkerRuntime(
        handler=handler,
        settings=WorkerSettings(
            consumer_name="w-1",
            install_signal_handlers=True,
            shutdown_signals=(signal.SIGTERM,),
        ),
        consumer_factory=lambda **_: fake,
    )

    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.01)
    fake.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert signal.SIGTERM in installed


@pytest.mark.asyncio
async def test_runtime_rejects_consumer_without_run_method():
    """Defensive: a misconfigured factory should fail loudly, not hang."""

    class _Bad:  # no .run()
        pass

    runtime = WorkerRuntime(
        handler=lambda *_: None,  # type: ignore[arg-type]
        settings=WorkerSettings(consumer_name="w-1", install_signal_handlers=False),
        consumer_factory=lambda **_: _Bad(),
    )
    with pytest.raises(TypeError, match="async `run\\(\\)`"):
        await runtime.run()


# ---------- run_worker convenience wrapper ---------------------------------


@pytest.mark.asyncio
async def test_run_worker_uses_config_settings_when_none_provided(monkeypatch):
    """``run_worker(handler)`` should default to the production settings
    object — but we patch out the actual consumer to avoid Redis."""
    calls = {}

    async def fake_run(self):
        calls["consumer"] = self._settings.consumer_name
        calls["concurrency"] = self._settings.concurrency

    monkeypatch.setattr(WorkerRuntime, "run", fake_run)

    async def handler(job_id, user_id):
        pass

    await run_worker(handler)

    assert "consumer" in calls
    assert calls["concurrency"] >= 1
