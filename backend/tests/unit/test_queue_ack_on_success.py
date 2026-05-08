"""Unit tests for ADR-0040 / m7-pr27c — ACK-on-success queue semantics + DLQ.

Covers QueueConsumer._dispatch behaviour under both flag states:
  1. Flag OFF  → legacy always-ACK-in-finally (handler raise still ACKs).
  2. Flag ON  + handler success  → record dedup row + ACK.
  3. Flag ON  + handler raises   → no ACK, no dedup row (next reclaim will retry).
  4. Flag ON  + handler raises at max delivery → DLQ + ACK.
  5. Flag ON  + delivery_count > max on entry → DLQ + ACK without invoking handler.
  6. Flag ON  + duplicate dedup insert → ACK + skip (no error).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.queue import GROUP_NAME, STREAM_KEY, QueueConsumer


# ── Fakes ────────────────────────────────────────────────────────────────


class _UniqueViolation(Exception):
    pass

    def __str__(self) -> str:
        return "duplicate key value violates unique constraint"


class _FakeRedis:
    """Minimal sync-style Redis stub matching what queue.py calls via asyncio.to_thread."""

    def __init__(self) -> None:
        self.acked: list[str] = []
        self.xadds: list[tuple[str, dict[str, Any]]] = []
        # delivery counts keyed by msg_id; default 1 if not set
        self.delivery_counts: dict[str, int] = {}

    def xack(self, stream: str, group: str, msg_id: str) -> int:
        assert stream == STREAM_KEY
        assert group == GROUP_NAME
        self.acked.append(msg_id)
        return 1

    def xadd(self, stream: str, fields: dict[str, Any]) -> str:
        self.xadds.append((stream, dict(fields)))
        return f"id-{len(self.xadds)}"

    def xpending_range(self, stream, group, *, min, max, count):
        n = self.delivery_counts.get(min, 1)
        # Return shape mirroring redis-py: list of dicts.
        return [{"message_id": min, "consumer": "worker-1", "time_since_delivered": 0, "times_delivered": n}]


@dataclass
class _FakeTable:
    parent: "_FakeDBClient"
    _row: dict[str, Any] | None = None

    def insert(self, row):
        self._row = row
        return self

    def execute(self):
        assert self._row is not None
        key = (self._row["consumer"], self._row["msg_id"])
        if key in self.parent.existing_keys:
            raise _UniqueViolation()
        self.parent.inserts.append(dict(self._row))
        self.parent.existing_keys.add(key)
        return type("R", (), {"data": [dict(self._row)]})()


@dataclass
class _FakeDBClient:
    inserts: list[dict[str, Any]] = field(default_factory=list)
    existing_keys: set[tuple[str, str]] = field(default_factory=set)

    def table(self, name: str) -> _FakeTable:
        assert name == "processed_queue_events", name
        return _FakeTable(parent=self)


@dataclass
class _FakeDB:
    client: _FakeDBClient = field(default_factory=_FakeDBClient)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def fake_db(monkeypatch) -> _FakeDB:
    db = _FakeDB()
    # patch app.core.database.get_db to return our fake
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_db", lambda: db)
    return db


@pytest.fixture
def flag_off(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ff_queue_ack_on_success", False, raising=False)
    monkeypatch.setattr(settings, "queue_max_deliveries", 5, raising=False)


@pytest.fixture
def flag_on(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ff_queue_ack_on_success", True, raising=False)
    monkeypatch.setattr(settings, "queue_max_deliveries", 5, raising=False)


# ── Helpers ──────────────────────────────────────────────────────────────


async def _drain_tasks() -> None:
    """Yield repeatedly so asyncio.create_task callbacks finish."""
    for _ in range(20):
        await asyncio.sleep(0)


def _make_consumer(handler) -> QueueConsumer:
    return QueueConsumer(handler=handler, consumer_name="test-worker", concurrency=2)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_off_handler_raises_still_acks(fake_redis, fake_db, flag_off):
    """Legacy contract: handler exception still ACKs, no DLQ, no dedup row."""

    async def handler(job_id: str, user_id: str) -> None:
        raise RuntimeError("boom")

    consumer = _make_consumer(handler)
    await consumer._dispatch(fake_redis, "100-0", {"job_id": "j1", "user_id": "u1"})
    await _drain_tasks()

    assert fake_redis.acked == ["100-0"]
    assert fake_redis.xadds == []
    assert fake_db.client.inserts == []


@pytest.mark.asyncio
async def test_flag_on_success_records_dedup_and_acks(fake_redis, fake_db, flag_on):
    calls: list[tuple[str, str]] = []

    async def handler(job_id: str, user_id: str) -> None:
        calls.append((job_id, user_id))

    consumer = _make_consumer(handler)
    await consumer._dispatch(fake_redis, "200-0", {"job_id": "j2", "user_id": "u2"})
    await _drain_tasks()

    assert calls == [("j2", "u2")]
    assert fake_redis.acked == ["200-0"]
    assert fake_redis.xadds == []  # no DLQ
    assert fake_db.client.inserts == [
        {"consumer": GROUP_NAME, "msg_id": "200-0"}
    ]


@pytest.mark.asyncio
async def test_flag_on_handler_raises_no_ack_no_dedup(fake_redis, fake_db, flag_on):
    """First delivery, handler raises → leave pending for reclaim, no DLQ yet."""

    async def handler(job_id: str, user_id: str) -> None:
        raise RuntimeError("transient")

    consumer = _make_consumer(handler)
    fake_redis.delivery_counts["300-0"] = 1  # first delivery
    await consumer._dispatch(fake_redis, "300-0", {"job_id": "j3", "user_id": "u3"})
    await _drain_tasks()

    assert fake_redis.acked == []  # KEY: not ACKed → reclaim retries
    assert fake_redis.xadds == []  # KEY: not yet at max → no DLQ
    assert fake_db.client.inserts == []


@pytest.mark.asyncio
async def test_flag_on_handler_raises_at_max_dlqs(fake_redis, fake_db, flag_on):
    """Last allowed delivery, handler raises → DLQ + ACK off source."""

    async def handler(job_id: str, user_id: str) -> None:
        raise RuntimeError("poison")

    consumer = _make_consumer(handler)
    fake_redis.delivery_counts["400-0"] = 5  # = queue_max_deliveries
    await consumer._dispatch(fake_redis, "400-0", {"job_id": "j4", "user_id": "u4"})
    await _drain_tasks()

    assert fake_redis.acked == ["400-0"]  # ACK off source after DLQ
    assert len(fake_redis.xadds) == 1
    dlq_stream, dlq_fields = fake_redis.xadds[0]
    assert dlq_stream == "events:dlq"
    assert dlq_fields["consumer"] == GROUP_NAME
    assert dlq_fields["source_msg_id"] == "400-0"
    assert dlq_fields["job_id"] == "j4"
    assert "poison" in dlq_fields["reason"]
    assert fake_db.client.inserts == []  # never recorded as processed


@pytest.mark.asyncio
async def test_flag_on_over_max_dlqs_without_invoking_handler(fake_redis, fake_db, flag_on):
    """delivery_count > max on entry → DLQ + ACK, handler never called."""
    calls: list[tuple[str, str]] = []

    async def handler(job_id: str, user_id: str) -> None:
        calls.append((job_id, user_id))

    consumer = _make_consumer(handler)
    fake_redis.delivery_counts["500-0"] = 6  # > queue_max_deliveries
    await consumer._dispatch(fake_redis, "500-0", {"job_id": "j5", "user_id": "u5"})
    await _drain_tasks()

    assert calls == []  # KEY: handler never invoked
    assert fake_redis.acked == ["500-0"]
    assert len(fake_redis.xadds) == 1
    assert fake_redis.xadds[0][0] == "events:dlq"
    assert "max_deliveries_exceeded" in fake_redis.xadds[0][1]["reason"]


@pytest.mark.asyncio
async def test_flag_on_duplicate_dedup_still_acks(fake_redis, fake_db, flag_on):
    """Redelivery of an already-processed msg_id → handler runs, dedup raises
    duplicate, that's swallowed, ACK still happens."""
    calls: list[tuple[str, str]] = []

    async def handler(job_id: str, user_id: str) -> None:
        calls.append((job_id, user_id))

    # Pre-populate the dedup table with this msg_id (simulates a prior delivery
    # whose handler ran but ACK round-trip failed).
    fake_db.client.existing_keys.add((GROUP_NAME, "600-0"))

    consumer = _make_consumer(handler)
    await consumer._dispatch(fake_redis, "600-0", {"job_id": "j6", "user_id": "u6"})
    await _drain_tasks()

    # Handler still ran (we don't pre-check the dedup table — that's an
    # acceptable cost for the simpler post-hoc flow). What matters is:
    assert calls == [("j6", "u6")]
    assert fake_redis.acked == ["600-0"]  # ACKed despite dedup duplicate
    assert fake_redis.xadds == []  # no DLQ on duplicate


@pytest.mark.asyncio
async def test_malformed_message_acks_immediately(fake_redis, fake_db, flag_on):
    """Missing job_id/user_id → ACK + discard regardless of flag state."""
    calls: list[tuple[str, str]] = []

    async def handler(job_id: str, user_id: str) -> None:
        calls.append((job_id, user_id))

    consumer = _make_consumer(handler)
    await consumer._dispatch(fake_redis, "700-0", {"job_id": ""})
    await _drain_tasks()

    assert calls == []
    assert fake_redis.acked == ["700-0"]
    assert fake_db.client.inserts == []
