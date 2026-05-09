"""Tests for the SSE replay accessor on ``AgenticEventEmitter`` (P0-7).

Closes the gap identified in m12-pr04 where the agentic stream endpoint
emitted ``events_to_replay: 0`` as a placeholder. The replay endpoint now
calls :py:meth:`AgenticEventEmitter.get_events_after` to slice the
in-memory event store by sequence; these unit tests pin the contract.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from ai_engine.agents.agentic_event_emitter import AgenticEventEmitter
from ai_engine.agents.streaming_protocol import (
    AgentContext,
    EventSink,
    EventType,
    StageContext,
    StreamingConfig,
    StreamPriority,
)


class _CollectingSink(EventSink):
    def __init__(self) -> None:
        self.batches: List[Dict[str, Any]] = []

    async def send(self, event: Dict[str, Any]) -> None:  # type: ignore[override]
        self.batches.append(event)

    async def flush(self) -> None:  # type: ignore[override]
        return None

    async def close(self) -> None:  # type: ignore[override]
        return None


def _agent() -> AgentContext:
    return AgentContext(id="t", name="t", type="test")


def _stage() -> StageContext:
    return StageContext(name="t", iteration=1, depth=0)


@pytest.mark.asyncio
async def test_get_events_after_returns_only_higher_sequences() -> None:
    cfg = StreamingConfig(enable_event_persistence=True)
    emitter = AgenticEventEmitter(sink=_CollectingSink(), config=cfg, session_id="sess-1")

    for i in range(5):
        await emitter.emit(
            event_type=EventType.AGENT_SPAWNED,
            payload={"i": i},
            agent=_agent(),
            stage=_stage(),
            priority=StreamPriority.NORMAL,
        )

    after = emitter.get_events_after(2)
    seqs = [e["sequence"] for e in after]
    assert seqs == sorted(seqs), "replay must be ordered by sequence"
    assert all(s > 2 for s in seqs), f"got non-strict-greater sequences: {seqs}"
    # full replay
    full = emitter.get_events_after(-1)
    assert len(full) >= 5
    assert emitter.session_id == "sess-1"
    # current_sequence is the next-to-assign value, so at least len(emitted)
    assert emitter.current_sequence >= 5


@pytest.mark.asyncio
async def test_get_events_after_empty_when_persistence_disabled() -> None:
    cfg = StreamingConfig(enable_event_persistence=False)
    emitter = AgenticEventEmitter(sink=_CollectingSink(), config=cfg, session_id="sess-2")

    await emitter.emit(
        event_type=EventType.AGENT_SPAWNED,
        payload={},
        agent=_agent(),
        stage=_stage(),
        priority=StreamPriority.NORMAL,
    )

    assert emitter.get_events_after(-1) == []


@pytest.mark.asyncio
async def test_get_events_after_returns_shallow_copy() -> None:
    cfg = StreamingConfig(enable_event_persistence=True)
    emitter = AgenticEventEmitter(sink=_CollectingSink(), config=cfg, session_id="sess-3")

    for _ in range(3):
        await emitter.emit(
            event_type=EventType.AGENT_SPAWNED,
            payload={},
            agent=_agent(),
            stage=_stage(),
            priority=StreamPriority.NORMAL,
        )

    snapshot = emitter.get_events_after(-1)
    snapshot.clear()
    # Mutating the returned list must NOT corrupt the underlying store
    assert len(emitter.get_events_after(-1)) >= 3
