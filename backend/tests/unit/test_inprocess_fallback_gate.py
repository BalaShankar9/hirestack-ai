"""Tests for ADR-0038 (P0-2) — eliminate the unbounded in-process
dispatch fallback.

Three behaviours are guaranteed:

1. ``ff_inprocess_fallback`` OFF (production default) + Redis
   unavailable → job is finalised as ``failed`` with a retryable
   message; no in-process pipeline task is spawned.
2. Flag ON + capacity available → in-process execution starts
   (legacy behaviour preserved for dev / single-process deploys).
3. Flag ON + concurrency cap reached → job is finalised as
   ``failed``; no new in-process task is spawned.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Some test environments don't have the optional `python-pptx` extra installed.
# The PPT route eagerly imports it via `app.api.routes.__init__`. Stub it just
# enough to allow the import to succeed; this test never exercises PPT logic.
def _stub_module(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


for _m in (
    "pptx",
    "pptx.util",
    "pptx.dml.color",
    "pptx.enum.shapes",
    "pptx.enum.text",
    "pptx.chart.data",
    "pptx.enum.chart",
):
    _stub_module(_m)
# Provide a Presentation symbol so `from pptx import Presentation` resolves.
if not hasattr(sys.modules["pptx"], "Presentation"):
    sys.modules["pptx"].Presentation = MagicMock()  # type: ignore[attr-defined]
# Common attributes used at import time.
for _name, _attrs in {
    "pptx.util": ("Inches", "Pt", "Emu"),
    "pptx.dml.color": ("RGBColor",),
    "pptx.enum.shapes": ("MSO_SHAPE",),
    "pptx.enum.text": ("PP_ALIGN", "MSO_ANCHOR"),
    "pptx.chart.data": ("CategoryChartData",),
    "pptx.enum.chart": ("XL_CHART_TYPE", "XL_LEGEND_POSITION"),
}.items():
    mod = sys.modules[_name]
    for _a in _attrs:
        if not hasattr(mod, _a):
            setattr(mod, _a, MagicMock())


@pytest.fixture
def jobs_module():
    from app.api.routes.generate import jobs as jm

    jm._ACTIVE_GENERATION_TASKS.clear()
    return jm


@pytest.mark.asyncio
async def test_redis_unavailable_with_flag_off_fails_job(jobs_module):
    """ADR-0038: prod default — failure is durable, not silent."""
    finalize = AsyncMock()
    inprocess = MagicMock()

    from app.core.config import settings as app_settings

    async def _enqueue_fail(_job, _user):
        return False  # simulate Redis unavailable

    with patch.object(jobs_module, "_finalize_orphaned_job", finalize), \
         patch.object(jobs_module, "_start_generation_job_inprocess", inprocess), \
         patch("app.core.queue.enqueue_generation_job", _enqueue_fail), \
         patch.object(app_settings, "ff_inprocess_fallback", False, create=True):
        jobs_module._start_generation_job_legacy("job-1", "user-1")
        # Allow the inner _try_enqueue and _handle_redis_unavailable to run.
        for _ in range(5):
            await asyncio.sleep(0)

    inprocess.assert_not_called()
    finalize.assert_awaited_once()
    args, kwargs = finalize.call_args
    assert args[0] == "job-1"
    assert kwargs.get("status") == "failed"
    assert "queue is temporarily unavailable" in kwargs.get("error_message", "").lower()


@pytest.mark.asyncio
async def test_redis_unavailable_with_flag_on_uses_inprocess(jobs_module):
    """Flag ON → dev path still works."""
    finalize = AsyncMock()
    inprocess = MagicMock()

    from app.core.config import settings as app_settings

    async def _enqueue_fail(_job, _user):
        return False

    with patch.object(jobs_module, "_finalize_orphaned_job", finalize), \
         patch.object(jobs_module, "_start_generation_job_inprocess", inprocess), \
         patch("app.core.queue.enqueue_generation_job", _enqueue_fail), \
         patch.object(app_settings, "ff_inprocess_fallback", True, create=True):
        jobs_module._start_generation_job_legacy("job-2", "user-2")
        for _ in range(5):
            await asyncio.sleep(0)

    inprocess.assert_called_once_with("job-2", "user-2")
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_inprocess_saturated_fails_job_without_starting_task(jobs_module):
    """Bounded fallback: over-cap requests fail fast."""
    finalize = AsyncMock()
    runtime = AsyncMock()

    from app.core.config import settings as app_settings

    # Pre-fill _ACTIVE_GENERATION_TASKS to the cap so the next call is over.
    cap = 2
    sentinel_tasks: list[asyncio.Task] = []
    for i in range(cap):
        async def _noop():
            await asyncio.sleep(3600)
        t = asyncio.create_task(_noop())
        sentinel_tasks.append(t)
        jobs_module._ACTIVE_GENERATION_TASKS[f"sentinel-{i}"] = t

    try:
        with patch.object(jobs_module, "_finalize_orphaned_job", finalize), \
             patch.object(jobs_module, "_run_generation_job_via_runtime", runtime), \
             patch.object(app_settings, "inprocess_max_concurrent", cap, create=True), \
             patch.object(app_settings, "ff_inprocess_fallback", True, create=True):
            jobs_module._start_generation_job_inprocess("job-3", "user-3")
            for _ in range(3):
                await asyncio.sleep(0)

        # Pipeline runtime must NOT be invoked.
        runtime.assert_not_called()
        # The over-cap job must NOT be tracked.
        assert "job-3" not in jobs_module._ACTIVE_GENERATION_TASKS
        # Job must be finalised as failed.
        finalize.assert_awaited_once()
        args, kwargs = finalize.call_args
        assert args[0] == "job-3"
        assert kwargs.get("status") == "failed"
        assert "saturated" in kwargs.get("error_message", "").lower()
    finally:
        for t in sentinel_tasks:
            t.cancel()
        await asyncio.gather(*sentinel_tasks, return_exceptions=True)
        jobs_module._ACTIVE_GENERATION_TASKS.clear()


@pytest.mark.asyncio
async def test_inprocess_under_cap_starts_task(jobs_module):
    """Capacity available → task is registered (legacy behaviour)."""
    runtime = AsyncMock()

    from app.core.config import settings as app_settings

    with patch.object(jobs_module, "_run_generation_job_via_runtime", runtime), \
         patch.object(app_settings, "inprocess_max_concurrent", 4, create=True), \
         patch.object(app_settings, "ff_inprocess_fallback", True, create=True):
        jobs_module._start_generation_job_inprocess("job-4", "user-4")
        # Yield so the wrapped task starts.
        await asyncio.sleep(0)

    assert "job-4" in jobs_module._ACTIVE_GENERATION_TASKS
    # Drain
    task = jobs_module._ACTIVE_GENERATION_TASKS.get("job-4")
    if task is not None:
        await asyncio.wait_for(task, timeout=1.0)
    runtime.assert_awaited_once_with("job-4", "user-4")
