"""m11-pr38: queue/dispatch/bootstrap counters."""
from __future__ import annotations

import pytest

from app.core import queue_metrics as qm


@pytest.fixture(autouse=True)
def _reset():
    qm.reset_for_tests()
    yield
    qm.reset_for_tests()


def test_inc_queue_ack_per_consumer():
    qm.inc_queue_ack("gen_workers")
    qm.inc_queue_ack("gen_workers")
    qm.inc_queue_ack("outbox-relay")
    snap = qm.snapshot()
    assert snap["queue_ack_total"] == {"gen_workers": 2, "outbox-relay": 1}


def test_inc_queue_dlq_buckets_reasons():
    qm.inc_queue_dlq("gen_workers", "max_deliveries_exceeded (6>5)")
    qm.inc_queue_dlq("gen_workers", "max_deliveries_exceeded (10>5)")
    qm.inc_queue_dlq("outbox-relay", "handler raised: NoCredits")
    snap = qm.snapshot()
    assert snap["queue_dlq_total"][("gen_workers", "max_deliveries_exceeded")] == 2
    assert snap["queue_dlq_total"][("outbox-relay", "handler_error")] == 1


def test_bucket_reason_handles_empty():
    assert qm._bucket_reason("") == "handler_error"
    assert qm._bucket_reason("max_deliveries_exceeded") == "max_deliveries_exceeded"
    assert qm._bucket_reason("Boom") == "handler_error"


def test_set_queue_pending_clamps_negative():
    qm.set_queue_pending("gen_workers", -3)
    assert qm.snapshot()["queue_pending_redeliveries"]["gen_workers"] == 0
    qm.set_queue_pending("gen_workers", 7)
    assert qm.snapshot()["queue_pending_redeliveries"]["gen_workers"] == 7


def test_inc_dispatch_fallback_kinds():
    qm.inc_dispatch_fallback("redis_unavailable_dropped")
    qm.inc_dispatch_fallback("inprocess_fallback")
    qm.inc_dispatch_fallback("inprocess_fallback")
    qm.inc_dispatch_fallback("temporal_failed")
    snap = qm.snapshot()
    assert snap["generation_dispatch_fallback_total"] == {
        "redis_unavailable_dropped": 1,
        "inprocess_fallback": 2,
        "temporal_failed": 1,
    }


def test_set_bootstrap_inflight():
    qm.set_bootstrap_inflight(3)
    assert qm.snapshot()["bootstrap_tasks_inflight"] == 3
    qm.set_bootstrap_inflight(0)
    assert qm.snapshot()["bootstrap_tasks_inflight"] == 0
    qm.set_bootstrap_inflight(-1)
    assert qm.snapshot()["bootstrap_tasks_inflight"] == 0


def test_inc_bootstrap_failure_strips_id_suffix():
    """Cardinality bound: per-job suffix must be stripped."""
    qm.inc_bootstrap_failure("gen-bootstrap-enqueue:abc-123")
    qm.inc_bootstrap_failure("gen-bootstrap-enqueue:def-456")
    qm.inc_bootstrap_failure("gen-bootstrap-temporal:ghi-789")
    snap = qm.snapshot()
    assert snap["bootstrap_task_failures_total"] == {
        "gen-bootstrap-enqueue": 2,
        "gen-bootstrap-temporal": 1,
    }


def test_snapshot_shape_stable():
    """main.py /metrics depends on these exact keys."""
    snap = qm.snapshot()
    assert set(snap) == {
        "queue_ack_total",
        "queue_dlq_total",
        "queue_pending_redeliveries",
        "generation_dispatch_fallback_total",
        "bootstrap_tasks_inflight",
        "bootstrap_task_failures_total",
    }


def test_increments_never_raise_on_none_or_garbage():
    """Observability must never break a request path."""
    qm.inc_queue_ack(None)  # type: ignore[arg-type]
    qm.inc_queue_dlq(None, None)  # type: ignore[arg-type]
    qm.inc_dispatch_fallback(None)  # type: ignore[arg-type]
    qm.inc_bootstrap_failure(None)  # type: ignore[arg-type]
    qm.set_bootstrap_inflight("not-an-int")  # type: ignore[arg-type]
    qm.set_queue_pending("c", "not-an-int")  # type: ignore[arg-type]
    # snapshot still works
    qm.snapshot()


def test_metrics_endpoint_exposes_all_six_families():
    """Pin the /metrics text output: all six metric names must appear
    even when counters are zero (HELP/TYPE lines are still emitted)."""
    import inspect
    import backend.main as m  # type: ignore

    src = inspect.getsource(m.prometheus_metrics)
    for marker in (
        "hirestack_queue_ack_total",
        "hirestack_queue_dlq_total",
        "hirestack_queue_pending_redeliveries",
        "hirestack_generation_dispatch_fallback_total",
        "hirestack_bootstrap_tasks_inflight",
        "hirestack_bootstrap_task_failures_total",
    ):
        assert marker in src, f"/metrics missing m11-pr38 marker: {marker}"
