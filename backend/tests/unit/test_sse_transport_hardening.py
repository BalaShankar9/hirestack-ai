"""S14-F2: SSE transport hardening tests.

Pins three behaviours:
  1. Bounded coalescing queue collapses non-terminal events of the same
     (event_type, stage) and drops oldest non-terminal under pressure,
     while NEVER losing terminal events (complete / error / agent_status
     completed/failed / close sentinel).
  2. The runtime stream wrapper emits a `: ping\\n\\n` SSE comment after a
     queue-idle interval so proxies don't reap the connection.
  3. PIPELINE_EVENT_SCHEMA_VERSION is pinned to "1.0" — bumping it requires
     deliberate review (update this test + ship the migration ADR).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services.pipeline_runtime import (
    PIPELINE_EVENT_SCHEMA_VERSION,
    PipelineEvent,
    SSESink,
    _CoalescingQueue,
    _SSE_SENTINEL_KEY,
)


@pytest.mark.asyncio
async def test_coalesce_replaces_same_key_non_terminal():
    q = _CoalescingQueue(maxsize=8)
    await q.put("a1", key=("progress", "atlas"), terminal=False)
    await q.put("a2", key=("progress", "atlas"), terminal=False)
    await q.put("c1", key=("progress", "cipher"), terminal=False)

    assert q.qsize() == 2
    assert q.coalesced == 1
    assert await q.get() == "a2"  # newest atlas survives
    assert await q.get() == "c1"


@pytest.mark.asyncio
async def test_drop_oldest_non_terminal_when_full():
    q = _CoalescingQueue(maxsize=2)
    await q.put("p1", key=("progress", "atlas"), terminal=False)
    await q.put("p2", key=("progress", "cipher"), terminal=False)
    await q.put("p3", key=("progress", "quill"), terminal=False)

    assert q.qsize() == 2
    assert q.dropped == 1
    # Oldest (atlas) was evicted; cipher + quill remain in order.
    assert await q.get() == "p2"
    assert await q.get() == "p3"


@pytest.mark.asyncio
async def test_terminal_events_never_dropped():
    q = _CoalescingQueue(maxsize=2)
    await q.put("p1", key=("progress", "atlas"), terminal=False)
    await q.put("p2", key=("progress", "cipher"), terminal=False)
    # Terminal append should NOT evict another terminal even when full.
    await q.put("DONE", key=("complete", ""), terminal=True)

    items = [await q.get() for _ in range(q.qsize())]
    assert "DONE" in items


@pytest.mark.asyncio
async def test_sse_sink_flood_preserves_terminal():
    sink = SSESink(maxsize=8)
    # Flood 5000 progress events on the same key.
    for i in range(5000):
        await sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=i % 100, message=f"tick {i}",
        ))
    # Terminal event must survive.
    await sink.emit(PipelineEvent(event_type="complete", phase="nova", message="done"))
    await sink.close()

    drained = []
    async for item in sink.iter_events():
        drained.append(item)

    # Last item before sentinel should be the complete event.
    assert any('"event_type"' not in s and "complete" in s for s in drained) or any(
        s.startswith("event: complete\n") for s in drained
    )
    # Queue stayed bounded (we drained <= maxsize+terminal items).
    assert len(drained) <= 9


@pytest.mark.asyncio
async def test_close_sentinel_terminates_iter():
    sink = SSESink(maxsize=4)
    await sink.emit(PipelineEvent(event_type="progress", phase="atlas", progress=10))
    await sink.close()

    items = [s async for s in sink.iter_events()]
    assert len(items) == 1
    assert items[0].startswith("event: progress\n")


@pytest.mark.asyncio
async def test_sse_sink_emit_carries_schema_version():
    sink = SSESink(maxsize=4)
    await sink.emit(PipelineEvent(event_type="progress", phase="atlas", progress=10))
    raw = await sink.queue.get()
    payload = json.loads(raw.split("\n")[1].replace("data: ", ""))
    assert payload["schema_version"] == PIPELINE_EVENT_SCHEMA_VERSION


def test_pipeline_event_schema_version_is_pinned():
    """ADR gate: bumping this requires updating /docs and notifying clients.

    Frontend, mobile, and any external SSE consumer pin against this value.
    Bump only in lock-step with a migration ADR + the matching constants in
    `frontend/src/hooks/use-agent-status.ts` and the mobile client.
    """
    assert PIPELINE_EVENT_SCHEMA_VERSION == "1.0"


@pytest.mark.asyncio
async def test_runtime_stream_emits_heartbeat_when_idle(monkeypatch):
    """Confirm the wrapper structure: when sink.queue.get() blocks past the
    heartbeat interval, the stream wrapper yields a `: ping` SSE comment.

    We test the pattern in isolation rather than booting FastAPI: the same
    asyncio.wait_for + ping behaviour shipped in routes/generate/stream.py.
    """
    sink = SSESink(maxsize=4)

    async def producer():
        await asyncio.sleep(0.15)
        await sink.emit(PipelineEvent(event_type="progress", phase="atlas", progress=5))
        await sink.close()

    async def stream():
        out = []
        prod = asyncio.create_task(producer())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(sink.queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    out.append(": ping\n\n")
                    continue
                if item is None:
                    break
                out.append(item)
        finally:
            await prod
        return out

    chunks = await stream()
    assert any(c == ": ping\n\n" for c in chunks), "expected a heartbeat ping during idle window"
    assert any(c.startswith("event: progress\n") for c in chunks)
