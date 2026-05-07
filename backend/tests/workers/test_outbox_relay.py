"""Tests for the outbox relay worker (PR m3-pr9).

Uses fake supabase RPC + fake redis. Real DB function behaviour
(FOR UPDATE SKIP LOCKED) is exercised in the migration; here we only
verify the orchestration: claim → publish → mark; failure → record.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.workers.outbox_relay import OutboxRelay, RelayConfig, STREAM_PREFIX


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    data: Any = None


@dataclass
class _RpcCall:
    fn: str
    params: dict[str, Any]


class _FakeSupabase:
    def __init__(self) -> None:
        self.calls: list[_RpcCall] = []
        # Queue of return values for outbox_claim_batch — list[list[row]].
        self.claim_queue: list[list[dict[str, Any]]] = []

    def rpc(self, fn: str, params: dict[str, Any]) -> "_FakeRpc":
        self.calls.append(_RpcCall(fn=fn, params=dict(params)))
        return _FakeRpc(parent=self, fn=fn)

    def calls_for(self, fn: str) -> list[_RpcCall]:
        return [c for c in self.calls if c.fn == fn]


@dataclass
class _FakeRpc:
    parent: _FakeSupabase
    fn: str

    def execute(self) -> _Response:
        if self.fn == "outbox_claim_batch":
            data = self.parent.claim_queue.pop(0) if self.parent.claim_queue else []
            return _Response(data=data)
        return _Response(data=None)


class _FakeRedis:
    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.xadds: list[tuple[str, dict[str, str]]] = []
        self._fail_on = fail_on or set()

    async def xadd(self, name: str, fields: dict[str, str]) -> str:
        if name in self._fail_on:
            raise RuntimeError("redis offline")
        self.xadds.append((name, dict(fields)))
        return f"id-{len(self.xadds)}"


def _row(
    *,
    event_type: str = "aim.source.created",
    publish_attempts: int = 1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "org_id": str(uuid.uuid4()),
        "occurred_at": "2026-05-07T12:00:00+00:00",
        "idempotency_key": None,
        "payload": payload or {"k": "v"},
        "publish_attempts": publish_attempts,
    }


# ---------------------------------------------------------------------------
# drain_once — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_once_returns_zero_when_outbox_empty() -> None:
    supa = _FakeSupabase()
    supa.claim_queue.append([])
    relay = OutboxRelay(supa, _FakeRedis())

    assert await relay.drain_once() == 0
    assert supa.calls_for("outbox_mark_published") == []


@pytest.mark.asyncio
async def test_drain_once_publishes_and_marks_each_row() -> None:
    supa = _FakeSupabase()
    rows = [_row(event_type="aim.source.created"), _row(event_type="generation.requested")]
    supa.claim_queue.append(rows)
    redis = _FakeRedis()
    relay = OutboxRelay(supa, redis)

    n = await relay.drain_once()

    assert n == 2
    assert len(redis.xadds) == 2
    streams = {name for name, _ in redis.xadds}
    assert streams == {f"{STREAM_PREFIX}aim.source.created", f"{STREAM_PREFIX}generation.requested"}
    # Payload is JSON-encoded inside the stream record.
    _, fields = redis.xadds[0]
    assert json.loads(fields["payload"]) == {"k": "v"}
    assert fields["event_id"] == rows[0]["event_id"]

    marks = supa.calls_for("outbox_mark_published")
    assert len(marks) == 2
    assert {c.params["p_event_id"] for c in marks} == {r["event_id"] for r in rows}
    assert supa.calls_for("outbox_record_failure") == []


# ---------------------------------------------------------------------------
# drain_once — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_once_records_failure_when_xadd_raises() -> None:
    supa = _FakeSupabase()
    row = _row(event_type="aim.source.created", publish_attempts=3)
    supa.claim_queue.append([row])
    redis = _FakeRedis(fail_on={f"{STREAM_PREFIX}aim.source.created"})
    relay = OutboxRelay(supa, redis, config=RelayConfig(max_attempts=10))

    n = await relay.drain_once()

    assert n == 0
    failures = supa.calls_for("outbox_record_failure")
    assert len(failures) == 1
    assert failures[0].params["p_event_id"] == row["event_id"]
    assert failures[0].params["p_max_attempts"] == 10
    assert "redis offline" in failures[0].params["p_error"]
    assert supa.calls_for("outbox_mark_published") == []


@pytest.mark.asyncio
async def test_drain_once_partial_failure_marks_only_succeeding_rows() -> None:
    supa = _FakeSupabase()
    good = _row(event_type="aim.source.created")
    bad = _row(event_type="generation.requested")
    supa.claim_queue.append([good, bad])
    redis = _FakeRedis(fail_on={f"{STREAM_PREFIX}generation.requested"})
    relay = OutboxRelay(supa, redis)

    n = await relay.drain_once()

    assert n == 1
    marks = supa.calls_for("outbox_mark_published")
    assert len(marks) == 1
    assert marks[0].params["p_event_id"] == good["event_id"]

    fails = supa.calls_for("outbox_record_failure")
    assert len(fails) == 1
    assert fails[0].params["p_event_id"] == bad["event_id"]


@pytest.mark.asyncio
async def test_drain_once_truncates_long_error_message() -> None:
    supa = _FakeSupabase()
    supa.claim_queue.append([_row()])

    class _NoisyRedis:
        async def xadd(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("x" * 5000)

    relay = OutboxRelay(supa, _NoisyRedis())
    await relay.drain_once()

    failures = supa.calls_for("outbox_record_failure")
    assert len(failures) == 1
    assert len(failures[0].params["p_error"]) <= 1000


# ---------------------------------------------------------------------------
# claim wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_passes_configured_batch_size() -> None:
    supa = _FakeSupabase()
    supa.claim_queue.append([])
    relay = OutboxRelay(supa, _FakeRedis(), config=RelayConfig(batch_size=17))

    await relay.drain_once()

    claims = supa.calls_for("outbox_claim_batch")
    assert len(claims) == 1
    assert claims[0].params == {"p_batch_size": 17}


# ---------------------------------------------------------------------------
# run() loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_drains_until_stopped() -> None:
    supa = _FakeSupabase()
    supa.claim_queue.append([_row()])
    supa.claim_queue.append([])  # second claim returns empty → relay sleeps
    redis = _FakeRedis()
    # idle_sleep tiny so test finishes fast.
    relay = OutboxRelay(supa, redis, config=RelayConfig(idle_sleep_s=0.01))

    task = asyncio.create_task(relay.run())
    await asyncio.sleep(0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=1.0)

    # Published the one row from the first claim.
    assert len(redis.xadds) == 1
    # Looped at least twice.
    assert len(supa.calls_for("outbox_claim_batch")) >= 2


@pytest.mark.asyncio
async def test_run_recovers_when_claim_raises() -> None:
    class _BoomSupabase(_FakeSupabase):
        def __init__(self) -> None:
            super().__init__()
            self.boom_count = 0

        def rpc(self, fn: str, params: dict[str, Any]) -> _FakeRpc:
            if fn == "outbox_claim_batch" and self.boom_count == 0:
                self.boom_count += 1
                raise RuntimeError("db hiccup")
            return super().rpc(fn, params)

    supa = _BoomSupabase()
    supa.claim_queue.append([])
    relay = OutboxRelay(
        supa,
        _FakeRedis(),
        config=RelayConfig(idle_sleep_s=0.01, error_sleep_s=0.01),
    )

    task = asyncio.create_task(relay.run())
    await asyncio.sleep(0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=1.0)

    # First call raised; relay must have retried and reached the empty claim.
    assert supa.boom_count == 1
    assert len(supa.calls_for("outbox_claim_batch")) >= 1
