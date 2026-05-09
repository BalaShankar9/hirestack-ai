"""DLQ contract tests for the generic Redis Streams consumer (m12-pr15).

The happy path and "max_deliveries_exceeded via reclaim" path are covered
by ``backend/tests/core/events/test_stream_consumer.py``. This file pins
the DLQ *contract* — the things downstream tooling (`scripts/ops/dlq_replay.py`,
the operator runbook, and the queue_metrics snapshot) depend on:

1. Every DLQ entry has the full 5-field schema with the documented types.
2. The source message is XACKed *after* the DLQ XADD (so a crash between
   the two leaves a duplicate in DLQ rather than a silently-dropped message).
3. Reasons that exceed 500 chars are truncated (cardinality / log size).
4. ``inc_queue_dlq`` is called with the bucketed reason on every DLQ.
5. The "delivery_attempt > max_deliveries" inline branch (separate from
   the "handler raised on final attempt" branch) actually fires.
6. Bytes-typed Redis fields decode losslessly into the DLQ ``event`` JSON.
7. A DLQ entry is round-trip-decodable by the replay tool's
   ``_build_replay_payload``.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.core import queue_metrics as qm
from app.core.events.consumer import (
    DLQ_STREAM,
    ConsumerConfig,
    StreamConsumer,
)


# --- Minimal fakes (kept independent of the existing test module so this
# --- file can be read in isolation as the DLQ-contract pin) ---------------


class _FakeRedis:
    def __init__(self) -> None:
        self.read_queues: dict[str, list[list[tuple[str, dict[str, Any]]]]] = {}
        self.claim_queues: dict[str, list[list[tuple[str, dict[str, Any]]]]] = {}
        self.acked: list[tuple[str, str, str]] = []
        self.xadds: list[tuple[str, dict[str, str]]] = []
        self._ops: list[str] = []  # ordered log of ack/xadd for ordering tests

    async def xgroup_create(self, name, groupname, id="$", mkstream=True):
        return True

    async def xreadgroup(self, groupname, consumername, streams, count=10, block=0):
        out = []
        for stream in streams:
            q = self.read_queues.setdefault(stream, [])
            if q:
                out.append((stream, q.pop(0)))
        return out

    async def xautoclaim(
        self, name, groupname, consumername, min_idle_time, start_id="0-0", count=10
    ):
        q = self.claim_queues.setdefault(name, [])
        return ("0-0", q.pop(0) if q else [])

    async def xack(self, name, groupname, *ids):
        for i in ids:
            self.acked.append((name, groupname, i))
            self._ops.append(f"ack:{name}:{i}")
        return len(ids)

    async def xadd(self, name, fields):
        self.xadds.append((name, dict(fields)))
        self._ops.append(f"xadd:{name}")
        return f"id-{len(self.xadds)}"


class _FakeSupabase:
    """Inert dedup table — DLQ tests should never reach the insert path."""

    def table(self, name: str):
        raise AssertionError(
            f"DLQ-path tests should not record consumed events; got table={name!r}"
        )


def _msg(
    *, payload: dict[str, Any] | None = None, encode_bytes: bool = False
) -> tuple[str, dict[str, Any]]:
    fields = {
        "event_id": str(uuid.uuid4()),
        "event_type": "generation.completed",
        "event_version": "1",
        "org_id": str(uuid.uuid4()),
        "occurred_at": "2026-05-09T12:00:00+00:00",
        "payload": json.dumps(payload or {"k": "v"}),
    }
    if encode_bytes:
        fields = {k.encode(): v.encode() for k, v in fields.items()}
    return (f"{int(uuid.uuid4().int >> 100)}-0", fields)


def _make_consumer(redis, supa, handler, *, max_deliveries: int = 2) -> StreamConsumer:
    return StreamConsumer(
        redis=redis,
        supabase=supa,
        config=ConsumerConfig(
            name="dlq_test_consumer",
            streams=("events:generation.completed",),
            block_ms=0,
            batch_size=10,
            max_deliveries=max_deliveries,
            reclaim_idle_ms=0,
        ),
        handler=handler,
    )


@pytest.fixture(autouse=True)
def _reset_metrics():
    qm.reset_for_tests()
    yield
    qm.reset_for_tests()


# --- Tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_dlq_entry_has_full_5_field_schema() -> None:
    """Replay tool + runbook depend on this exact field set."""
    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("boom")

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    assert len(redis.xadds) == 1
    stream, dlq = redis.xadds[0]
    assert stream == DLQ_STREAM
    assert set(dlq.keys()) == {
        "consumer",
        "source_stream",
        "source_msg_id",
        "reason",
        "event",
    }
    assert dlq["consumer"] == "dlq_test_consumer"
    assert dlq["source_stream"] == "events:generation.completed"
    assert dlq["source_msg_id"] == msg_id
    assert isinstance(dlq["reason"], str) and dlq["reason"]
    # ``event`` must be a JSON string holding the original event.
    decoded = json.loads(dlq["event"])
    assert decoded["event_id"] == fields["event_id"]
    assert decoded["event_type"] == "generation.completed"


@pytest.mark.asyncio
async def test_dlq_xadd_happens_before_source_xack() -> None:
    """Crash-safety invariant: a crash between the two leaves a DLQ
    duplicate (recoverable) rather than a silently-dropped message."""
    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("boom")

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    xadd_idx = next(i for i, op in enumerate(redis._ops) if op.startswith("xadd:"))
    ack_idx = next(
        i
        for i, op in enumerate(redis._ops)
        if op.startswith(f"ack:events:generation.completed:{msg_id}")
    )
    assert xadd_idx < ack_idx, redis._ops


@pytest.mark.asyncio
async def test_dlq_reason_truncated_to_500_chars() -> None:
    """Bounded log size & metric label cardinality."""
    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("x" * 10_000)

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    _, dlq = redis.xadds[0]
    assert len(dlq["reason"]) == 500


@pytest.mark.asyncio
async def test_dlq_increments_queue_dlq_metric() -> None:
    """The Prometheus snapshot must record one bucketed DLQ event."""
    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("downstream 503")

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    snap = qm.snapshot()
    dlq_keys = [k for k in snap["queue_dlq_total"] if k[0] == "dlq_test_consumer"]
    assert len(dlq_keys) == 1
    # Total across all buckets must be exactly 1.
    assert sum(snap["queue_dlq_total"][k] for k in dlq_keys) == 1
    # The corresponding ack must also be counted.
    assert snap["queue_ack_total"]["dlq_test_consumer"] == 1


@pytest.mark.asyncio
async def test_dlq_inline_when_delivery_attempt_already_exceeds() -> None:
    """The ``delivery_attempt > max_deliveries`` branch is distinct from
    the ``handler raised on final attempt`` branch — pin both so a future
    refactor doesn't collapse them silently."""
    redis = _FakeRedis()
    handler_calls: list[Any] = []

    async def handler(ev):
        handler_calls.append(ev)

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    # max_deliveries=1 + reclaim path (delivery_attempt=2) => inline DLQ.
    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=1)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    assert handler_calls == [], "handler must NOT be invoked when over budget"
    assert len(redis.xadds) == 1
    _, dlq = redis.xadds[0]
    assert dlq["reason"] == "max_deliveries_exceeded"


@pytest.mark.asyncio
async def test_dlq_decodes_bytes_fields_losslessly() -> None:
    """Real redis-py returns bytes; the DLQ ``event`` payload must end up
    as a JSON-decodable string of the original event_id."""
    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("bytes path")

    msg_id, fields = _msg(encode_bytes=True)
    expected_event_id = fields[b"event_id"].decode()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    _, dlq = redis.xadds[0]
    decoded = json.loads(dlq["event"])
    assert decoded["event_id"] == expected_event_id


@pytest.mark.asyncio
async def test_dlq_entry_replays_via_dlq_replay_tool() -> None:
    """End-to-end-shape contract: DLQ payload feeds the replay tool's
    ``_build_replay_payload`` cleanly. If this breaks, the operator
    runbook ('replay a stuck event') breaks."""
    from scripts.ops.dlq_replay import _build_replay_payload  # type: ignore

    redis = _FakeRedis()

    async def handler(_):
        raise RuntimeError("transient")

    msg_id, fields = _msg(payload={"job_id": "abc-123"})
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, _FakeSupabase(), handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    _, dlq = redis.xadds[0]
    rebuilt = _build_replay_payload(dlq)
    # Replay payload must carry the original event_id and have all values
    # as str (Redis stream field type).
    assert rebuilt["event_id"] == fields["event_id"]
    assert all(isinstance(v, str) for v in rebuilt.values())


@pytest.mark.asyncio
async def test_no_dlq_when_handler_eventually_succeeds() -> None:
    """Negative control: a successful handler on the reclaim attempt
    must not produce a DLQ entry, but DOES produce a source-stream ack."""
    redis = _FakeRedis()

    async def handler(_):
        return None

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = StreamConsumer(
        redis=redis,
        supabase=_NoopSupabase(),
        config=ConsumerConfig(
            name="dlq_test_consumer",
            streams=("events:generation.completed",),
            block_ms=0,
            batch_size=10,
            max_deliveries=5,
            reclaim_idle_ms=0,
        ),
        handler=handler,
    )
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    assert redis.xadds == []
    assert (
        "events:generation.completed",
        "dlq_test_consumer",
        msg_id,
    ) in redis.acked
    assert qm.snapshot()["queue_dlq_total"] == {}


# Lightweight no-op supabase for the negative-control test only — the
# success path DOES record the consumed event.
class _NoopSupabase:
    def table(self, _name: str):
        return self

    def insert(self, _row):
        return self

    def execute(self):
        return type("R", (), {"data": []})()
