"""Prometheus-style counters/gauges for queue + generation + bootstrap.

m11-pr38 (M7/M9 deferred — counters). Plain process-local int counters
keyed by labels; safe under the GIL for `+= 1` increments. Read by
``backend/main.py`` /metrics endpoint to render Prometheus exposition
text. No external prometheus_client dependency yet — that swap lands in
m11-pr41.

Surface:

* ``inc_queue_ack(consumer)`` — bump on every successful XACK.
* ``inc_queue_dlq(consumer, reason)`` — bump every time _dead_letter
  XADDs to ``events:dlq``. ``reason`` is bucketed coarsely
  (``max_deliveries_exceeded`` vs ``handler_error``) to keep cardinality
  bounded.
* ``inc_dispatch_fallback(kind)`` — bump when the generation dispatch
  path falls back away from its primary route. Kinds:
  ``redis_unavailable_dropped`` (queue down + flag off),
  ``inprocess_fallback`` (queue down + flag on),
  ``temporal_failed`` (Temporal strangler failed → legacy path).
* ``inc_bootstrap_failure(task)`` — bump when a registered bootstrap
  coroutine raises in its done-callback.
* ``set_bootstrap_inflight(n)`` — set the in-flight gauge (called from
  /metrics scrape with ``len(_BOOTSTRAP_TASKS)``).
* ``snapshot()`` — return a dict of all counters/gauges for the /metrics
  formatter.
* ``reset_for_tests()`` — clear all state (test-only).

All functions are best-effort: they never raise. A bug in observability
must never break a request path.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

# ── module state ──────────────────────────────────────────────────────

# counter: queue_ack_total{consumer}
_queue_ack: dict[str, int] = defaultdict(int)
# counter: queue_dlq_total{consumer,reason_bucket}
_queue_dlq: dict[tuple[str, str], int] = defaultdict(int)
# gauge: queue_pending_redeliveries{consumer} — sampled at scrape time
_queue_pending: dict[str, int] = defaultdict(int)
# counter: generation_dispatch_fallback_total{kind}
_dispatch_fallback: dict[str, int] = defaultdict(int)
# gauge: bootstrap_tasks_inflight (no labels — global to the registry)
_bootstrap_inflight: int = 0
# counter: bootstrap_task_failures_total{task}
_bootstrap_failures: dict[str, int] = defaultdict(int)


# ── reason bucketing ──────────────────────────────────────────────────

_MAX_DELIVERIES_PREFIX = "max_deliveries_exceeded"


def _bucket_reason(reason: str) -> str:
    """Coarsen a free-form DLQ reason into a low-cardinality bucket.

    ``max_deliveries_exceeded (6>5)`` → ``max_deliveries_exceeded``.
    Anything else → ``handler_error``.
    """
    if not reason:
        return "handler_error"
    if reason.startswith(_MAX_DELIVERIES_PREFIX):
        return _MAX_DELIVERIES_PREFIX
    return "handler_error"


# ── increments / setters ──────────────────────────────────────────────


def inc_queue_ack(consumer: str) -> None:
    try:
        _queue_ack[consumer or "unknown"] += 1
    except Exception:
        pass


def inc_queue_dlq(consumer: str, reason: str) -> None:
    try:
        _queue_dlq[(consumer or "unknown", _bucket_reason(reason))] += 1
    except Exception:
        pass


def set_queue_pending(consumer: str, n: int) -> None:
    try:
        _queue_pending[consumer or "unknown"] = max(0, int(n))
    except Exception:
        pass


def inc_dispatch_fallback(kind: str) -> None:
    try:
        _dispatch_fallback[kind or "unknown"] += 1
    except Exception:
        pass


def set_bootstrap_inflight(n: int) -> None:
    global _bootstrap_inflight
    try:
        _bootstrap_inflight = max(0, int(n))
    except Exception:
        pass


def inc_bootstrap_failure(task: str) -> None:
    try:
        # Strip the trailing ":<id>" suffix that ``_track_bootstrap``
        # appends so cardinality stays bounded across millions of jobs.
        # e.g. "gen-bootstrap-enqueue:abc-123" → "gen-bootstrap-enqueue".
        family = (task or "unknown").split(":", 1)[0]
        _bootstrap_failures[family] += 1
    except Exception:
        pass


# ── snapshot for /metrics ─────────────────────────────────────────────


def snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable view of all metrics.

    Shape (stable — main.py depends on it):

    ```
    {
      "queue_ack_total":          {consumer: int, ...},
      "queue_dlq_total":          {(consumer, reason_bucket): int, ...},
      "queue_pending_redeliveries":{consumer: int, ...},
      "generation_dispatch_fallback_total": {kind: int, ...},
      "bootstrap_tasks_inflight": int,
      "bootstrap_task_failures_total": {task_family: int, ...},
    }
    ```
    """
    return {
        "queue_ack_total": dict(_queue_ack),
        "queue_dlq_total": dict(_queue_dlq),
        "queue_pending_redeliveries": dict(_queue_pending),
        "generation_dispatch_fallback_total": dict(_dispatch_fallback),
        "bootstrap_tasks_inflight": int(_bootstrap_inflight),
        "bootstrap_task_failures_total": dict(_bootstrap_failures),
    }


def reset_for_tests() -> None:
    """Test-only — clear all counters/gauges."""
    global _bootstrap_inflight
    _queue_ack.clear()
    _queue_dlq.clear()
    _queue_pending.clear()
    _dispatch_fallback.clear()
    _bootstrap_failures.clear()
    _bootstrap_inflight = 0
