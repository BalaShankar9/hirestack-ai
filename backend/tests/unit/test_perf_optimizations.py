"""Anchor tests for Wave-1 performance optimizations.

Covers:
1. PipelineRuntime._await_company_intel — recon overlap with Atlas.
2. /metrics endpoint exposes cache hit-rate + per-phase latency gauges.
3. Phase latency aggregation rolls correctly through MetricsCollector.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.services import pipeline_runtime as pr_module
from app.services.pipeline_runtime import (
    CollectorSink,
    ExecutionMode,
    PipelineRuntime,
    RuntimeConfig,
)


# ── Recon overlap ──────────────────────────────────────────────────────

def _make_runtime() -> PipelineRuntime:
    cfg = RuntimeConfig(mode=ExecutionMode.SYNC, user_id="u1")
    return PipelineRuntime(config=cfg, event_sink=CollectorSink())


@pytest.mark.asyncio
async def test_await_company_intel_returns_task_result_once():
    rt = _make_runtime()

    async def _intel():
        await asyncio.sleep(0)
        return {"summary": "hi", "confidence": "high"}

    rt._intel_task = asyncio.create_task(_intel())
    rt._intel_started_at = 0.0  # unused when task already running

    out1 = await rt._await_company_intel(timeout=5.0)
    out2 = await rt._await_company_intel(timeout=5.0)
    assert out1 == {"summary": "hi", "confidence": "high"}
    assert out2 == out1, "second await must return cached value, not re-run task"
    assert rt._intel_resolved is True


@pytest.mark.asyncio
async def test_await_company_intel_handles_missing_task():
    rt = _make_runtime()
    rt._intel_task = None
    out = await rt._await_company_intel(timeout=1.0)
    assert out == {}
    assert rt._intel_resolved is True


@pytest.mark.asyncio
async def test_await_company_intel_handles_timeout_cleanly():
    rt = _make_runtime()

    async def _slow():
        await asyncio.sleep(2.0)
        return {"summary": "never"}

    rt._intel_task = asyncio.create_task(_slow())
    rt._intel_started_at = 0.0

    # Trick remaining-budget calc by forcing short timeout
    out = await rt._await_company_intel(timeout=0.05)
    assert out == {}
    assert rt._intel_resolved is True
    # Task must be cancelled so we don't leak coroutines
    assert rt._intel_task.cancelled() or rt._intel_task.done()
    # Warning event must be emitted on the sink
    sink = rt.sink
    assert any(
        e.phase == "recon" and "timed out" in e.message.lower()
        for e in getattr(sink, "events", [])
    )


@pytest.mark.asyncio
async def test_await_company_intel_handles_task_exception():
    rt = _make_runtime()

    async def _boom():
        raise RuntimeError("intel boom")

    rt._intel_task = asyncio.create_task(_boom())
    rt._intel_started_at = 0.0

    out = await rt._await_company_intel(timeout=2.0)
    assert out == {}
    assert rt._intel_resolved is True
    failed_modules = [m["module"] for m in rt._failed_modules]
    assert "company_intel" in failed_modules


# ── Anchor: recon section in pipeline_runtime no longer awaits inline ──


def test_recon_block_does_not_await_intel_inline():
    """The recon block must launch intel as a background task and let
    Atlas overlap; awaiting inline would defeat the entire optimization."""
    src = inspect.getsource(pr_module)
    # The defining marker for the new path
    assert "self._intel_task = intel_task" in src
    assert "self._intel_started_at = time.perf_counter()" in src
    # The first downstream consumer must call the helper
    assert "await self._await_company_intel(" in src
    # Old inline block must be gone
    assert "asyncio.shield(intel_task),\n                timeout=30," not in src


# ── Metrics endpoint exposes new gauges ────────────────────────────────


def test_metrics_endpoint_exposes_cache_and_phase_gauges():
    """The /metrics route source must expose cache + per-phase metrics."""
    import backend.main as backend_main  # type: ignore[import-not-found]
    src = inspect.getsource(backend_main)
    # Cache hit-rate
    assert "hirestack_ai_cache_hits_total" in src
    assert "hirestack_ai_cache_hit_rate" in src
    assert "from ai_engine.cache import get_all_cache_stats" in src
    # Per-phase latency
    assert "hirestack_phase_duration_p50_ms" in src
    assert "hirestack_phase_duration_p95_ms" in src
    assert "hirestack_phase_success_rate" in src


# ── MetricsCollector phase aggregation works end-to-end ────────────────


def test_metrics_collector_records_phase_latency():
    from app.core.metrics import MetricsCollector, StageMetric

    MetricsCollector.reset()
    coll = MetricsCollector.get()
    for i in range(3):
        coll.record_stage(StageMetric(
            pipeline_name="runtime_sync",
            stage_name="recon",
            started_at=1000.0 + i,
            finished_at=1000.5 + i,
            success=True,
        ))
    stats = coll.get_stage_stats()
    assert "recon" in stats
    assert stats["recon"]["count"] == 3
    assert stats["recon"]["success_rate"] == 1.0
    assert stats["recon"]["p50_ms"] == 500
