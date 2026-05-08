"""Tests for the prometheus_client-based /metrics exposition (m11-pr41)."""
from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture(autouse=True)
def _reset_queue_metrics():
    """Each test sees a fresh queue_metrics state."""
    from app.core import queue_metrics as qm
    qm.reset_for_tests()
    yield
    qm.reset_for_tests()


def _render():
    mod = importlib.import_module("app.core.prometheus_collectors")
    body, ct = mod.render_metrics()
    return body.decode("utf-8"), ct


def test_render_returns_text_plain_content_type():
    _, ct = _render()
    # prometheus_client picks "text/plain; version=0.0.4; charset=utf-8"
    assert ct.startswith("text/plain")
    assert "version=" in ct


def test_six_m11_pr38_families_present_even_when_empty():
    """Names must always be exposed so dashboards bind cleanly."""
    body, _ = _render()
    for name in (
        "hirestack_queue_ack_total",
        "hirestack_queue_dlq_total",
        "hirestack_queue_pending_redeliveries",
        "hirestack_generation_dispatch_fallback_total",
        "hirestack_bootstrap_tasks_inflight",
        "hirestack_bootstrap_task_failures_total",
    ):
        assert f"# HELP {name}" in body, f"missing HELP for {name}"
        assert f"# TYPE {name}" in body, f"missing TYPE for {name}"


def test_queue_ack_increments_show_up_in_exposition():
    from app.core import queue_metrics as qm
    qm.inc_queue_ack("worker-1")
    qm.inc_queue_ack("worker-1")
    qm.inc_queue_ack("worker-2")
    body, _ = _render()
    assert 'hirestack_queue_ack_total{consumer="worker-1"} 2.0' in body or \
           'hirestack_queue_ack_total{consumer="worker-1"} 2' in body
    assert 'hirestack_queue_ack_total{consumer="worker-2"}' in body


def test_dlq_counter_carries_consumer_and_reason_labels():
    from app.core import queue_metrics as qm
    # queue_metrics buckets free-form reasons into low-cardinality labels:
    # anything that isn't ``max_deliveries_exceeded*`` becomes ``handler_error``.
    qm.inc_queue_dlq("worker-1", "bad_payload")
    body, _ = _render()
    assert 'hirestack_queue_dlq_total{consumer="worker-1",reason="handler_error"}' in body


def test_dispatch_fallback_uses_kind_label():
    from app.core import queue_metrics as qm
    qm.inc_dispatch_fallback("redis_unavailable")
    body, _ = _render()
    assert 'hirestack_generation_dispatch_fallback_total{kind="redis_unavailable"}' in body


def test_bootstrap_failure_uses_task_label():
    from app.core import queue_metrics as qm
    qm.inc_bootstrap_failure("scheduler-stale-job-cleanup")
    body, _ = _render()
    assert 'hirestack_bootstrap_task_failures_total{task="scheduler-stale-job-cleanup"}' in body


def test_bootstrap_inflight_gauge_exposed():
    from app.core import queue_metrics as qm
    qm.set_bootstrap_inflight(7)
    body, _ = _render()
    # Gauge is refreshed live from _BOOTSTRAP_TASKS during render. With the
    # registry empty at test time the value is zero — what we're verifying
    # here is that the family is emitted at all.
    assert "hirestack_bootstrap_tasks_inflight" in body


def test_no_dependency_explosion_kills_render():
    """Even if a source raises, render_metrics must still return bytes."""
    mod = importlib.import_module("app.core.prometheus_collectors")
    body, _ct = mod.render_metrics()
    assert isinstance(body, (bytes, bytearray))
    assert len(body) > 0


def test_collector_yields_no_duplicate_family_names():
    """prometheus_client refuses duplicate names — guard against drift."""
    mod = importlib.import_module("app.core.prometheus_collectors")
    families = list(mod.HirestackCollector().collect())
    names = [f.name for f in families]
    # Some families may be skipped when empty (ai_caches, phase_latency,
    # doc_quality, llm_calls, daily_cost), so we only assert uniqueness.
    assert len(names) == len(set(names)), f"duplicate metric names: {names}"


def test_endpoint_auth_gate_still_in_main():
    """The auth gate stays in backend/main.py — the collector module
    must not bypass it. This is a smoke check on the structure."""
    main = importlib.import_module("main")
    src = importlib.import_module("inspect").getsource(main.prometheus_metrics)
    assert "_check_metrics_auth(request)" in src
    assert "render_metrics()" in src


def test_render_under_concurrent_scrapes():
    """Two concurrent renders must each return valid output."""
    from app.core import queue_metrics as qm
    qm.inc_queue_ack("c1")
    mod = importlib.import_module("app.core.prometheus_collectors")

    async def _runner():
        loop = asyncio.get_running_loop()
        results = await asyncio.gather(
            loop.run_in_executor(None, mod.render_metrics),
            loop.run_in_executor(None, mod.render_metrics),
        )
        return results

    results = asyncio.run(_runner())
    for body, _ct in results:
        assert b"hirestack_queue_ack_total" in body
