"""Phase B.1 — verify make_workflow_event_emitter wires Phase A.2
ContextVar emits into the WorkflowEventStore (and thus into the
generation_job_events table)."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_engine.agent_events import (
    chain_agent_scope,
    emit_cache_hit,
    emit_evidence_added,
    emit_policy_decision,
    emit_tool_call,
    emit_tool_result,
    event_emitter_scope,
)
from ai_engine.agents.workflow_runtime import (
    WorkflowState,
    make_workflow_event_emitter,
)


def _make_state() -> WorkflowState:
    return WorkflowState(
        workflow_id="wf-1",
        pipeline_name="cv_generation",
        user_id="u-1",
        job_id="job-1",
        application_id="app-1",
    )


@pytest.mark.asyncio
async def test_bridge_translates_tool_call_and_result_to_store_emit() -> None:
    state = _make_state()
    store = MagicMock()
    captured: list[dict[str, Any]] = []

    async def capture_emit(state_arg, **kwargs):  # type: ignore[override]
        captured.append({"state": state_arg, **kwargs})

    store.emit = capture_emit

    bridge = make_workflow_event_emitter(store, state)
    with event_emitter_scope(bridge), chain_agent_scope("recon", stage="research"):
        emit_tool_call("github.fetch", {"repo": "x"})
        emit_tool_result("github.fetch", {"items": 3}, latency_ms=420, success=True)
    # Drain background tasks scheduled by emit_*.
    for _ in range(5):
        await asyncio.sleep(0)

    names = [c["event_name"] for c in captured]
    assert "tool_call" in names
    assert "tool_result" in names

    call = next(c for c in captured if c["event_name"] == "tool_call")
    assert call["stage"] == "research"
    assert call["payload"]["agent"] == "recon"
    assert "Calling github.fetch" in call["message"]

    res = next(c for c in captured if c["event_name"] == "tool_result")
    assert res["latency_ms"] == 420
    assert res["status"] == "completed"


@pytest.mark.asyncio
async def test_bridge_marks_cache_hit_in_message() -> None:
    state = _make_state()
    captured: list[dict[str, Any]] = []
    store = MagicMock()

    async def capture_emit(state_arg, **kwargs):
        captured.append(kwargs)

    store.emit = capture_emit

    bridge = make_workflow_event_emitter(store, state)
    with event_emitter_scope(bridge), chain_agent_scope("quill"):
        emit_tool_result(
            "ai.drafting", {"keys": ["html"]},
            latency_ms=2, cache_hit=True, success=True,
        )
        emit_cache_hit("ai_response", key_preview="abc123")
    for _ in range(5):
        await asyncio.sleep(0)

    by_name = {c["event_name"]: c for c in captured}
    assert "cached" in by_name["tool_result"]["message"]
    assert by_name["cache_hit"]["payload"]["agent"] == "quill"
    assert by_name["cache_hit"]["status"] == "completed"


@pytest.mark.asyncio
async def test_bridge_passes_through_evidence_and_policy_events() -> None:
    state = _make_state()
    captured: list[dict[str, Any]] = []
    store = MagicMock()

    async def capture_emit(state_arg, **kwargs):
        captured.append(kwargs)

    store.emit = capture_emit

    bridge = make_workflow_event_emitter(store, state)
    with event_emitter_scope(bridge), chain_agent_scope("cipher"):
        emit_evidence_added(
            tier="tier_1", source="github", text="user.profile",
        )
        emit_policy_decision(
            "model_cascade_failover",
            reason="gemini-1.5-pro failed → trying gemini-2.0-flash",
            metadata={"failed": "gemini-1.5-pro", "next": "gemini-2.0-flash"},
        )
    for _ in range(5):
        await asyncio.sleep(0)

    names = [c["event_name"] for c in captured]
    assert "evidence_added" in names
    assert "policy_decision" in names

    pd = next(c for c in captured if c["event_name"] == "policy_decision")
    assert "gemini-1.5-pro failed" in pd["message"]
    assert pd["payload"]["agent"] == "cipher"
