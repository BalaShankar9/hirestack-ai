"""
prometheus_client-based exposition for /metrics. (m11-pr41 / TD-3)

The legacy exposition in ``backend/main.py::prometheus_metrics`` was
hand-rolled string concatenation. That worked, but every new metric
required get-it-right-by-hand HELP/TYPE banding plus careful label
escaping, and the family was easy to break by accident.

This module wraps the existing snapshot sources (MetricsCollector,
queue_metrics, circuit_breaker, cache stats, etc.) in a ``Collector``
that yields ``GaugeMetricFamily`` / ``CounterMetricFamily`` instances
on each scrape. The endpoint then serialises via
``prometheus_client.exposition.generate_latest()``.

CONTRACT (do not break):
- All metric NAMES from the previous exposition are preserved 1:1.
- All label NAMES and VALUES are preserved 1:1.
- Snapshot sources are unchanged — this module only re-shapes their
  output for the wire.

Because the underlying state lives in process-local singletons
(``MetricsCollector``, ``queue_metrics`` counters, ``_breakers``,
``_daily_tracker``), we use the ``CollectorRegistry`` per-scrape model
rather than ``prometheus_client``'s default metric instances. That
keeps the multi-worker story honest: each gunicorn worker exposes its
own slice. A future PR can flip on PROMETHEUS_MULTIPROC_DIR to
aggregate across workers without touching this module.
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
)


# ── label-safe sanitisers ──────────────────────────────────────────────
# Match the quirks of the legacy exposition exactly so dashboards keep
# working: dashes/dots/slashes become underscores in label values.

def _safe(value: str) -> str:
    return (value or "").replace("-", "_").replace(" ", "_")


def _safe_model(value: str) -> str:
    return (value or "unknown").replace("-", "_").replace(".", "_").replace("/", "_")


# ── individual family yielders ─────────────────────────────────────────
# Each function tolerates a missing/exploded source so a single broken
# import never empties the whole /metrics response. Failures are silent
# by design (matches the legacy try/except blocks). Callers wrap the
# whole thing in another try/except for the same reason.


def _yield_pipeline_metrics() -> Iterable:
    try:
        from app.core.metrics import MetricsCollector
        stats = MetricsCollector.get().get_stats()
    except Exception:
        return

    g_active = GaugeMetricFamily(
        "hirestack_active_jobs",
        "Number of in-flight generation jobs",
    )
    g_active.add_metric([], int(stats.get("active_jobs", 0) or 0))
    yield g_active

    c_failovers = CounterMetricFamily(
        "hirestack_model_failovers_total",
        "Cumulative model cascade failovers",
    )
    c_failovers.add_metric([], int(stats.get("model_failovers_total", 0) or 0))
    yield c_failovers

    c_runs = CounterMetricFamily(
        "hirestack_pipeline_runs_total",
        "Pipeline runs per pipeline",
        labels=["pipeline"],
    )
    g_success = GaugeMetricFamily(
        "hirestack_pipeline_success_rate",
        "Pipeline success rate",
        labels=["pipeline"],
    )
    g_p50 = GaugeMetricFamily(
        "hirestack_pipeline_duration_p50_ms",
        "Pipeline median duration (ms)",
        labels=["pipeline"],
    )
    g_p95 = GaugeMetricFamily(
        "hirestack_pipeline_duration_p95_ms",
        "Pipeline 95th-pct duration (ms)",
        labels=["pipeline"],
    )
    for pipeline_name, ps in (stats.get("pipelines") or {}).items():
        sn = _safe(pipeline_name)
        c_runs.add_metric([sn], int(ps.get("count", 0) or 0))
        g_success.add_metric([sn], float(ps.get("success_rate", 0) or 0))
        g_p50.add_metric([sn], int(ps.get("duration_p50_ms", 0) or 0))
        g_p95.add_metric([sn], int(ps.get("duration_p95_ms", 0) or 0))
    yield c_runs
    yield g_success
    yield g_p50
    yield g_p95

    c_errors = CounterMetricFamily(
        "hirestack_errors_total",
        "Errors per error class",
        labels=["error_class"],
    )
    for error_class, ecount in (stats.get("error_counts") or {}).items():
        c_errors.add_metric([str(error_class)], int(ecount or 0))
    yield c_errors


def _yield_circuit_breakers() -> Iterable:
    try:
        from app.core.circuit_breaker import _breakers, CircuitState
    except Exception:
        return
    if not _breakers:
        return

    state_code = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}
    g_state = GaugeMetricFamily(
        "hirestack_circuit_breaker_state",
        "Circuit breaker state (0=closed,1=half_open,2=open)",
        labels=["name"],
    )
    g_failures = GaugeMetricFamily(
        "hirestack_circuit_breaker_failures",
        "Failure count per breaker",
        labels=["name"],
    )
    for name, br in _breakers.items():
        sn = _safe_model(name)
        g_state.add_metric([sn], state_code.get(br.state, 0))
        g_failures.add_metric([sn], int(getattr(br, "failure_count", 0) or 0))
    yield g_state
    yield g_failures


def _yield_queue_depth() -> Iterable:
    try:
        from app.core.queue import queue_depth
        depth = max(0, int(queue_depth() or 0))
    except Exception:
        return
    g = GaugeMetricFamily(
        "hirestack_queue_depth",
        "Pending jobs in Redis Streams queue",
    )
    g.add_metric([], depth)
    yield g


def _yield_queue_and_bootstrap_counters() -> Iterable:
    """The six families landed in m11-pr38. Snapshot keys are the contract."""
    try:
        from app.core import queue_metrics as qm
    except Exception:
        return

    # Refresh inflight gauge from the live registry.
    try:
        from app.api.routes.generate.jobs import _BOOTSTRAP_TASKS as _bt
        qm.set_bootstrap_inflight(len(_bt))
    except Exception:
        pass

    # Refresh queue_pending_redeliveries from XPENDING summary.
    try:
        from app.core.database import get_redis as _gr
        from app.core.queue import STREAM_KEY as _sk, GROUP_NAME as _gn
        r = _gr()
        if r is not None:
            summary = r.xpending(_sk, _gn)
            pending = 0
            if isinstance(summary, dict):
                pending = int(summary.get("pending", 0) or 0)
            elif isinstance(summary, (list, tuple)) and summary:
                pending = int(summary[0] or 0)
            qm.set_queue_pending(_gn, pending)
    except Exception:
        pass

    snap = qm.snapshot()

    c_ack = CounterMetricFamily(
        "hirestack_queue_ack_total",
        "Successful XACKs per consumer",
        labels=["consumer"],
    )
    for consumer, n in (snap.get("queue_ack_total") or {}).items():
        c_ack.add_metric([str(consumer)], int(n or 0))
    yield c_ack

    c_dlq = CounterMetricFamily(
        "hirestack_queue_dlq_total",
        "Messages routed to events:dlq per consumer and reason bucket",
        labels=["consumer", "reason"],
    )
    for (consumer, reason), n in (snap.get("queue_dlq_total") or {}).items():
        c_dlq.add_metric([str(consumer), str(reason)], int(n or 0))
    yield c_dlq

    g_pending = GaugeMetricFamily(
        "hirestack_queue_pending_redeliveries",
        "In-flight (PEL) messages awaiting ACK or reclaim",
        labels=["consumer"],
    )
    for consumer, n in (snap.get("queue_pending_redeliveries") or {}).items():
        g_pending.add_metric([str(consumer)], int(n or 0))
    yield g_pending

    c_disp = CounterMetricFamily(
        "hirestack_generation_dispatch_fallback_total",
        "Times generation dispatch left its primary route",
        labels=["kind"],
    )
    for kind, n in (snap.get("generation_dispatch_fallback_total") or {}).items():
        c_disp.add_metric([str(kind)], int(n or 0))
    yield c_disp

    g_inflight = GaugeMetricFamily(
        "hirestack_bootstrap_tasks_inflight",
        "Currently-tracked fire-and-forget bootstrap coroutines",
    )
    g_inflight.add_metric([], int(snap.get("bootstrap_tasks_inflight", 0) or 0))
    yield g_inflight

    c_btf = CounterMetricFamily(
        "hirestack_bootstrap_task_failures_total",
        "Bootstrap coroutines that raised before completion",
        labels=["task"],
    )
    for task, n in (snap.get("bootstrap_task_failures_total") or {}).items():
        c_btf.add_metric([str(task)], int(n or 0))
    yield c_btf


def _yield_ai_caches() -> Iterable:
    try:
        from ai_engine.cache import get_all_cache_stats
        cache_stats = get_all_cache_stats() or {}
    except Exception:
        return

    c_hits = CounterMetricFamily(
        "hirestack_ai_cache_hits_total", "Cumulative cache hits per layer", labels=["layer"]
    )
    c_misses = CounterMetricFamily(
        "hirestack_ai_cache_misses_total", "Cumulative cache misses per layer", labels=["layer"]
    )
    g_rate = GaugeMetricFamily(
        "hirestack_ai_cache_hit_rate", "Hit rate percentage per cache layer", labels=["layer"]
    )
    g_size = GaugeMetricFamily(
        "hirestack_ai_cache_size", "Entries currently held per cache layer", labels=["layer"]
    )
    any_seen = False
    for layer_name, layer_stats in cache_stats.items():
        if not isinstance(layer_stats, dict):
            continue
        any_seen = True
        sn = _safe(layer_name)
        c_hits.add_metric([sn], int(layer_stats.get("hits", 0) or 0))
        c_misses.add_metric([sn], int(layer_stats.get("misses", 0) or 0))
        g_rate.add_metric([sn], float(layer_stats.get("hit_rate_pct", 0) or 0))
        g_size.add_metric([sn], int(layer_stats.get("size", 0) or 0))
    if any_seen:
        yield c_hits
        yield c_misses
        yield g_rate
        yield g_size


def _yield_phase_latency() -> Iterable:
    try:
        from app.core.metrics import MetricsCollector
        stage_stats = MetricsCollector.get().get_stage_stats() or {}
    except Exception:
        return
    if not stage_stats:
        return

    g_p50 = GaugeMetricFamily(
        "hirestack_phase_duration_p50_ms", "Median phase duration (ms)", labels=["phase"]
    )
    g_p95 = GaugeMetricFamily(
        "hirestack_phase_duration_p95_ms", "95th-pct phase duration (ms)", labels=["phase"]
    )
    g_sr = GaugeMetricFamily(
        "hirestack_phase_success_rate", "Phase success rate (0-1)", labels=["phase"]
    )
    for phase_name, ps in stage_stats.items():
        sn = _safe(phase_name)
        g_p50.add_metric([sn], int(ps.get("p50_ms", 0) or 0))
        g_p95.add_metric([sn], int(ps.get("p95_ms", 0) or 0))
        g_sr.add_metric([sn], float(ps.get("success_rate", 0) or 0))
    yield g_p50
    yield g_p95
    yield g_sr


def _yield_doc_quality() -> Iterable:
    try:
        from app.core.metrics import MetricsCollector
        dq = MetricsCollector.get().get_doc_quality_stats() or {}
    except Exception:
        return
    if not dq:
        return

    g_mean = GaugeMetricFamily("hirestack_doc_quality_mean", "Mean doc quality (0-100)", labels=["doc_type"])
    g_p50 = GaugeMetricFamily("hirestack_doc_quality_p50", "Median doc quality (0-100)", labels=["doc_type"])
    g_p95 = GaugeMetricFamily("hirestack_doc_quality_p95", "95th-pct doc quality (0-100)", labels=["doc_type"])
    g_min = GaugeMetricFamily("hirestack_doc_quality_min", "Min doc quality (0-100)", labels=["doc_type"])
    for doc_type, qs in dq.items():
        sn = _safe(doc_type)
        g_mean.add_metric([sn], float(qs.get("mean", 0) or 0))
        g_p50.add_metric([sn], int(qs.get("p50", 0) or 0))
        g_p95.add_metric([sn], int(qs.get("p95", 0) or 0))
        g_min.add_metric([sn], int(qs.get("min", 0) or 0))
    yield g_mean
    yield g_p50
    yield g_p95
    yield g_min


def _yield_llm_calls() -> Iterable:
    try:
        from app.core.metrics import MetricsCollector
        llm = MetricsCollector.get().get_llm_call_stats() or {}
    except Exception:
        return
    if not llm:
        return

    c_calls = CounterMetricFamily(
        "hirestack_llm_calls_total", "LLM calls per model and task type", labels=["model", "task_type"]
    )
    c_in = CounterMetricFamily(
        "hirestack_llm_tokens_in_total", "LLM input tokens per model and task type", labels=["model", "task_type"]
    )
    c_out = CounterMetricFamily(
        "hirestack_llm_tokens_out_total", "LLM output tokens per model and task type", labels=["model", "task_type"]
    )
    for _key, ls in llm.items():
        m = _safe_model(ls.get("model") or "unknown")
        t = _safe(ls.get("task_type") or "unknown")
        c_calls.add_metric([m, t], int(ls.get("calls", 0) or 0))
        c_in.add_metric([m, t], int(ls.get("tokens_in", 0) or 0))
        c_out.add_metric([m, t], int(ls.get("tokens_out", 0) or 0))
    yield c_calls
    yield c_in
    yield c_out


def _yield_daily_cost() -> Iterable:
    try:
        from ai_engine.api import _daily_tracker  # type: ignore
        s = _daily_tracker.stats
    except Exception:
        return
    g1 = GaugeMetricFamily("hirestack_ai_daily_cost_cents", "Estimated AI cost today (USD cents)")
    g1.add_metric([], int(round(float(s.get("total_cost_usd", 0) or 0) * 100)))
    yield g1
    g2 = GaugeMetricFamily("hirestack_ai_daily_calls_total", "Total AI calls today")
    g2.add_metric([], int(s.get("total_calls", 0) or 0))
    yield g2
    g3 = GaugeMetricFamily("hirestack_ai_daily_tokens_total", "Total AI tokens today")
    g3.add_metric([], int(s.get("total_tokens", 0) or 0))
    yield g3
    g4 = GaugeMetricFamily("hirestack_ai_daily_cache_hits_total", "Total cache hits today")
    g4.add_metric([], int(s.get("cache_hits", 0) or 0))
    yield g4


# ── the collector ──────────────────────────────────────────────────────


class HirestackCollector:
    """Single Collector that yields every Hirestack metric family.

    Registered with a fresh ``CollectorRegistry`` per scrape so the
    state in source singletons (queue_metrics, MetricsCollector, …)
    is read live without leaking process-default registry samples.
    """

    def collect(self):
        for fn in (
            _yield_pipeline_metrics,
            _yield_circuit_breakers,
            _yield_queue_depth,
            _yield_queue_and_bootstrap_counters,
            _yield_ai_caches,
            _yield_phase_latency,
            _yield_doc_quality,
            _yield_llm_calls,
            _yield_daily_cost,
        ):
            try:
                yield from fn()
            except Exception:
                # A broken source must NEVER take down /metrics.
                continue


def render_metrics() -> tuple[bytes, str]:
    """Render the full /metrics body. Returns (body, content_type).

    The endpoint handler stays in ``backend/main.py`` for auth gating;
    it just calls this and wraps the bytes in a Response.
    """
    from prometheus_client import CollectorRegistry
    from prometheus_client.exposition import generate_latest, CONTENT_TYPE_LATEST

    registry = CollectorRegistry()
    registry.register(HirestackCollector())
    return generate_latest(registry), CONTENT_TYPE_LATEST
