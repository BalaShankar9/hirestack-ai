"""Tests for the generic StreamConsumer scaffold (PR m3-pr10)."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.events.consumer import DLQ_STREAM, ConsumerConfig, StreamConsumer


# --- Fakes ----------------------------------------------------------------


class _FakeRedis:
    def __init__(self) -> None:
        self.read_queues: dict[str, list[list[tuple[str, dict[str, str]]]]] = {}
        self.claim_queues: dict[str, list[list[tuple[str, dict[str, str]]]]] = {}
        self.acked: list[tuple[str, str, str]] = []
        self.xadds: list[tuple[str, dict[str, str]]] = []
        self.groups_created: list[tuple[str, str]] = []

    async def xgroup_create(self, name, groupname, id="$", mkstream=True):
        if (name, groupname) in self.groups_created:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self.groups_created.append((name, groupname))
        return True

    async def xreadgroup(self, groupname, consumername, streams, count=10, block=0):
        out = []
        for stream in streams:
            queue = self.read_queues.setdefault(stream, [])
            if queue:
                out.append((stream, queue.pop(0)))
        return out

    async def xautoclaim(self, name, groupname, consumername, min_idle_time, start_id="0-0", count=10):
        queue = self.claim_queues.setdefault(name, [])
        msgs = queue.pop(0) if queue else []
        return ("0-0", msgs)

    async def xack(self, name, groupname, *ids):
        for i in ids:
            self.acked.append((name, groupname, i))
        return len(ids)

    async def xadd(self, name, fields):
        self.xadds.append((name, dict(fields)))
        return f"id-{len(self.xadds)}"


class _UniqueViolation(Exception):
    code = "23505"


@dataclass
class _FakeSupabase:
    inserts: list[dict[str, Any]] = field(default_factory=list)
    raise_unique: set[str] = field(default_factory=set)

    def table(self, name: str) -> "_FakeTable":
        assert name == "consumed_events", name
        return _FakeTable(parent=self)


@dataclass
class _FakeTable:
    parent: _FakeSupabase
    _row: dict[str, Any] | None = None

    def insert(self, row):
        self._row = row
        return self

    def execute(self):
        assert self._row is not None
        eid = self._row["event_id"]
        if eid in self.parent.raise_unique:
            raise _UniqueViolation("duplicate key value violates unique constraint")
        self.parent.inserts.append(dict(self._row))
        return type("R", (), {"data": [dict(self._row)]})()


def _msg(*, payload: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
    return (
        f"{int(uuid.uuid4().int >> 100)}-0",
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "generation.completed",
            "event_version": "1",
            "org_id": str(uuid.uuid4()),
            "occurred_at": "2026-05-07T12:00:00+00:00",
            "payload": json.dumps(payload or {"k": "v"}),
        },
    )


def _make_consumer(redis, supa, handler, *, max_deliveries: int = 3) -> StreamConsumer:
    return StreamConsumer(
        redis=redis,
        supabase=supa,
        config=ConsumerConfig(
            name="billing_usage",
            streams=("events:generation.completed",),
            block_ms=0,
            batch_size=10,
            max_deliveries=max_deliveries,
            reclaim_idle_ms=0,
        ),
        handler=handler,
    )


# --- Tests ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_called_then_message_acked_and_consumed_recorded() -> None:
    redis, supa, seen = _FakeRedis(), _FakeSupabase(), []

    async def handler(ev):
        seen.append(ev)

    msg_id, fields = _msg()
    redis.read_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, supa, handler)
    await consumer._ensure_groups()
    n = await consumer._read_new()

    assert n == 1
    assert seen[0]["event_id"] == fields["event_id"]
    assert seen[0]["payload"] == {"k": "v"}  # JSON-decoded
    assert supa.inserts == [{"consumer": "billing_usage", "event_id": fields["event_id"]}]
    assert redis.acked == [("events:generation.completed", "billing_usage", msg_id)]


@pytest.mark.asyncio
async def test_groups_created_with_mkstream_and_busygroup_swallowed() -> None:
    redis = _FakeRedis()
    consumer = _make_consumer(redis, _FakeSupabase(), lambda e: asyncio.sleep(0))
    await consumer._ensure_groups()
    await consumer._ensure_groups()  # second call is a no-op
    assert redis.groups_created == [("events:generation.completed", "billing_usage")]


@pytest.mark.asyncio
async def test_duplicate_event_acks_silently() -> None:
    redis, supa, calls = _FakeRedis(), _FakeSupabase(), []

    async def handler(ev):
        calls.append(ev["event_id"])

    msg_id, fields = _msg()
    supa.raise_unique.add(fields["event_id"])  # insert will raise 23505
    redis.read_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, supa, handler)
    await consumer._ensure_groups()
    await consumer._read_new()

    assert calls == [fields["event_id"]]
    assert supa.inserts == []
    assert redis.acked == [("events:generation.completed", "billing_usage", msg_id)]


@pytest.mark.asyncio
async def test_handler_exception_does_not_ack_or_record() -> None:
    redis, supa = _FakeRedis(), _FakeSupabase()

    async def handler(ev):
        raise RuntimeError("boom")

    msg_id, fields = _msg()
    redis.read_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, supa, handler, max_deliveries=3)
    await consumer._ensure_groups()
    await consumer._read_new()

    assert supa.inserts == []
    assert redis.acked == []  # left for XAUTOCLAIM
    assert redis.xadds == []


@pytest.mark.asyncio
async def test_dlq_after_max_deliveries_via_reclaim() -> None:
    redis, supa = _FakeRedis(), _FakeSupabase()

    async def handler(ev):
        raise RuntimeError("still broken")

    msg_id, fields = _msg()
    redis.claim_queues["events:generation.completed"] = [[(msg_id, fields)]]

    consumer = _make_consumer(redis, supa, handler, max_deliveries=2)
    await consumer._ensure_groups()
    await consumer._reclaim_pending()

    assert len(redis.xadds) == 1
    dlq_stream, dlq_fields = redis.xadds[0]
    assert dlq_stream == DLQ_STREAM
    assert dlq_fields["consumer"] == "billing_usage"
    assert dlq_fields["source_msg_id"] == msg_id
    assert "still broken" in dlq_fields["reason"]
    assert json.loads(dlq_fields["event"])["event_id"] == fields["event_id"]
    assert redis.acked == [("events:generation.completed", "billing_usage", msg_id)]


@pytest.mark.asyncio
async def test_event_without_event_id_is_acked_and_skipped() -> None:
    redis, supa, calls = _FakeRedis(), _FakeSupabase(), []

    async def handler(ev):
        calls.append(ev)

    msg_id = "1-0"
    redis.read_queues["events:generation.completed"] = [
        [(msg_id, {"event_type": "generation.completed", "payload": "{}"})]
    ]

    consumer = _make_consumer(redis, supa, handler)
    await consumer._ensure_groups()
    await consumer._read_new()

    assert calls == []
    assert redis.acked == [("events:generation.completed", "billing_usage", msg_id)]
    assert supa.inserts == []


@pytest.mark.asyncio
async def test_run_processes_then_stops() -> None:
    redis, supa, seen = _FakeRedis(), _FakeSupabase(), []

    async def handler(ev):
        seen.append(ev["event_id"])

    msg1, msg2 = _msg(), _msg()
    redis.read_queues["events:generation.completed"] = [[msg1], [msg2]]

    consumer = _make_consumer(redis, supa, handler)
    task = asyncio.create_task(consumer.run())
    for _ in range(20):
        if len(seen) >= 2:
            break
        await asyncio.sleep(0.01)
    consumer.request_stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert sorted(seen) == sorted([msg1[1]["event_id"], msg2[1]["event_id"]])
    assert len(redis.acked) == 2
