"""S14-F4: substep events.

Tests pin the contract for ``EventSink.emit_substep`` and the contextvar
emitter that ``SubAgent.safe_run`` uses to publish substep_started /
substep_completed / substep_failed events without an explicit kwarg.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from app.services.pipeline_runtime import (
    CollectorSink,
    PipelineEvent,
    SSESink,
    get_substep_emitter,
    reset_substep_emitter,
    set_substep_emitter,
)
from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


# ─── EventSink.emit_substep default routing ────────────────────────


@pytest.mark.asyncio
async def test_collector_sink_emits_started_and_completed():
    sink = CollectorSink()
    await sink.emit_substep(stage="quill", sub_agent="tone_calibrator", status="started")
    await sink.emit_substep(
        stage="quill", sub_agent="tone_calibrator", status="completed",
        latency_ms=42, data={"confidence": 0.9},
    )
    types = [e.event_type for e in sink.events]
    assert types == ["substep_started", "substep_completed"]
    completed = sink.events[1]
    assert completed.stage == "quill"
    assert completed.latency_ms == 42
    assert completed.data["sub_agent"] == "tone_calibrator"
    assert completed.data["confidence"] == 0.9


@pytest.mark.asyncio
async def test_sse_sink_serialises_substep_frames():
    sink = SSESink()
    await sink.emit_substep(stage="forge", sub_agent="keyword_strategist", status="started")
    await sink.emit_substep(
        stage="forge", sub_agent="keyword_strategist", status="completed",
        latency_ms=17,
    )
    await sink.close()
    frames = []
    async for chunk in sink.iter_events():
        frames.append(chunk)
    assert any("event: substep_started" in f for f in frames)
    assert any("event: substep_completed" in f for f in frames)
    assert any('"sub_agent": "keyword_strategist"' in f for f in frames)


# ─── SubAgent.safe_run emits via contextvar ────────────────────────


class _OkAgent(SubAgent):
    def __init__(self) -> None:
        super().__init__(name="ok_agent", ai_client=object())  # ai_client unused

    async def run(self, context: dict) -> SubAgentResult:
        return SubAgentResult(agent_name=self.name, data={"ok": True}, confidence=0.77)


class _BoomAgent(SubAgent):
    def __init__(self) -> None:
        super().__init__(name="boom_agent", ai_client=object())

    async def run(self, context: dict) -> SubAgentResult:
        raise RuntimeError("nope")


@pytest.mark.asyncio
async def test_safe_run_emits_started_and_completed_when_emitter_bound():
    captured: List[Dict[str, Any]] = []

    async def emitter(sub_agent: str, status: str, latency_ms: int,
                     message: str, data: Optional[Dict[str, Any]]) -> None:
        captured.append({
            "sub_agent": sub_agent, "status": status,
            "latency_ms": latency_ms, "data": data,
        })

    tok = set_substep_emitter(emitter)
    try:
        result = await _OkAgent().safe_run({})
    finally:
        reset_substep_emitter(tok)

    assert result.ok
    assert [c["status"] for c in captured] == ["started", "completed"]
    # confidence forwarded into the completed payload
    assert captured[1]["data"]["confidence"] == 0.77


@pytest.mark.asyncio
async def test_safe_run_emits_failed_on_exception():
    captured: List[Dict[str, Any]] = []

    async def emitter(sub_agent, status, latency_ms, message, data):
        captured.append({"status": status, "message": message})

    tok = set_substep_emitter(emitter)
    try:
        result = await _BoomAgent().safe_run({})
    finally:
        reset_substep_emitter(tok)

    assert not result.ok
    statuses = [c["status"] for c in captured]
    assert statuses == ["started", "failed"]
    assert "nope" in captured[1]["message"]


@pytest.mark.asyncio
async def test_safe_run_no_op_when_emitter_unset():
    # Ensure no contextvar leakage from earlier tests.
    assert get_substep_emitter() is None
    # Should not raise even though no emitter is bound.
    result = await _OkAgent().safe_run({})
    assert result.ok


@pytest.mark.asyncio
async def test_safe_run_swallows_emitter_errors():
    async def bad_emitter(*args, **kwargs):
        raise RuntimeError("emitter exploded")

    tok = set_substep_emitter(bad_emitter)
    try:
        result = await _OkAgent().safe_run({})
    finally:
        reset_substep_emitter(tok)
    assert result.ok  # emitter error must NOT break the agent


@pytest.mark.asyncio
async def test_substep_emitter_isolated_across_tasks():
    captured_a: List[str] = []
    captured_b: List[str] = []

    async def emitter_a(sub_agent, status, *_):
        captured_a.append(f"a:{sub_agent}:{status}")

    async def emitter_b(sub_agent, status, *_):
        captured_b.append(f"b:{sub_agent}:{status}")

    async def task_a():
        tok = set_substep_emitter(emitter_a)
        try:
            await _OkAgent().safe_run({})
        finally:
            reset_substep_emitter(tok)

    async def task_b():
        tok = set_substep_emitter(emitter_b)
        try:
            await _OkAgent().safe_run({})
        finally:
            reset_substep_emitter(tok)

    await asyncio.gather(task_a(), task_b())
    assert captured_a == ["a:ok_agent:started", "a:ok_agent:completed"]
    assert captured_b == ["b:ok_agent:started", "b:ok_agent:completed"]
