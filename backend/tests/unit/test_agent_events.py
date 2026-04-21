"""Unit tests for ai_engine.agent_events context-scoped emitter."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_engine.agent_events import (
    TimedTool,
    chain_agent_scope,
    emit_cache_hit,
    emit_evidence_added,
    emit_policy_decision,
    emit_tool_call,
    emit_tool_result,
    event_emitter_scope,
    get_current_chain_agent,
    get_event_emitter,
    reset_event_emitter,
    set_chain_agent,
    set_event_emitter,
)


class _Capture:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, payload))


@pytest.mark.asyncio
async def test_no_emitter_is_no_op() -> None:
    """Helpers should be safe to call when no emitter is bound."""
    assert get_event_emitter() is None
    emit_tool_call("foo")
    emit_tool_result("foo", success=True)
    emit_cache_hit("ai_response")
    emit_evidence_added(tier="VERBATIM", source="JD", text="hi")
    emit_policy_decision("retry", reason="rate-limited")
    # No exception, no events captured anywhere.


@pytest.mark.asyncio
async def test_emit_tool_call_and_result_round_trip() -> None:
    cap = _Capture()
    token = set_event_emitter(cap)
    try:
        emit_tool_call("github.search", {"q": "a" * 500}, agent="recon", stage="research")
        emit_tool_result(
            "github.search",
            {"items": list(range(20))},
            agent="recon",
            stage="research",
            latency_ms=830,
            cache_hit=False,
            success=True,
        )
        # Allow scheduled tasks to run.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        reset_event_emitter(token)

    names = [n for n, _ in cap.events]
    assert "tool_call" in names
    assert "tool_result" in names

    call_payload = next(p for n, p in cap.events if n == "tool_call")
    assert call_payload["tool"] == "github.search"
    assert call_payload["agent"] == "recon"
    assert call_payload["status"] == "running"
    # Long string in arguments must have been truncated.
    assert call_payload["arguments_preview"]["q"].endswith("…")

    result_payload = next(p for n, p in cap.events if n == "tool_result")
    assert result_payload["latency_ms"] == 830
    assert result_payload["status"] == "completed"
    assert result_payload["result_preview"]["items"].startswith("<list len=20")


@pytest.mark.asyncio
async def test_emit_tool_result_failure_carries_error() -> None:
    cap = _Capture()
    token = set_event_emitter(cap)
    try:
        emit_tool_result("scrape", success=False, error="timeout after 30s")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        reset_event_emitter(token)

    payload = cap.events[0][1]
    assert payload["status"] == "failed"
    assert payload["error"] == "timeout after 30s"


@pytest.mark.asyncio
async def test_event_emitter_scope_isolates_context() -> None:
    cap = _Capture()
    with event_emitter_scope(cap):
        emit_cache_hit("ai_response", saved_ms=120)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    # Outside the scope: no longer bound.
    assert get_event_emitter() is None

    # And we got the event from inside the scope.
    name, payload = cap.events[0]
    assert name == "cache_hit"
    assert payload["cache"] == "ai_response"
    assert payload["saved_ms"] == 120


@pytest.mark.asyncio
async def test_evidence_event_marks_cross_confirmation() -> None:
    cap = _Capture()
    with event_emitter_scope(cap):
        emit_evidence_added(
            tier="VERBATIM",
            source="JD",
            text="Requires Python 3.13+",
            confidence=0.95,
            sub_agent="recon",
            cross_confirmed=True,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    name, payload = cap.events[0]
    assert name == "evidence_added"
    assert payload["cross_confirmed"] is True
    assert payload["tier"] == "VERBATIM"
    assert "cross-confirmed" in payload["message"]


@pytest.mark.asyncio
async def test_policy_decision_emits_metadata() -> None:
    cap = _Capture()
    with event_emitter_scope(cap):
        emit_policy_decision(
            "skip_optional_chain",
            reason="degraded_mode",
            agent="orchestrator",
            metadata={"missing_key": "github_token"},
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    name, payload = cap.events[0]
    assert name == "policy_decision"
    assert payload["decision"] == "skip_optional_chain"
    assert payload["metadata"]["missing_key"] == "github_token"


@pytest.mark.asyncio
async def test_emitter_failure_does_not_break_caller() -> None:
    """If the emitter raises, the helper must swallow it."""

    async def bad_emitter(_name: str, _payload: dict[str, Any]) -> None:
        raise RuntimeError("kaboom")

    with event_emitter_scope(bad_emitter):
        emit_tool_call("noop")
        # Ensure scheduled task runs and the exception is caught silently.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    # No exception escaped to here — test passes by completing.


@pytest.mark.asyncio
async def test_timed_tool_async_context_manager_emits_pair() -> None:
    cap = _Capture()
    with event_emitter_scope(cap):
        async with TimedTool("ai.complete", agent="quill", arguments={"model": "gpt-4o"}) as t:
            t.result_summary = {"tokens": 1234}
            t.cache_hit = False
            await asyncio.sleep(0.01)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    names = [n for n, _ in cap.events]
    assert names == ["tool_call", "tool_result"]
    result = cap.events[1][1]
    assert result["tool"] == "ai.complete"
    assert result["status"] == "completed"
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_chain_agent_scope_attributes_nested_emits() -> None:
    cap = _Capture()
    with event_emitter_scope(cap):
        with chain_agent_scope("recon", stage="research"):
            emit_tool_call("github.fetch")
            emit_evidence_added(tier="VERBATIM", source="JD", text="hi")
        # Outside the scope: agent falls back to "pipeline".
        emit_tool_call("after.scope")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    by_name = {n: p for n, p in cap.events}
    assert "tool_call" in by_name
    # First tool_call inside scope was tagged recon.
    inside = [p for n, p in cap.events if n == "tool_call" and p["tool"] == "github.fetch"][0]
    assert inside["agent"] == "recon"
    assert inside["stage"] == "research"
    outside = [p for n, p in cap.events if n == "tool_call" and p["tool"] == "after.scope"][0]
    assert outside["agent"] == "pipeline"
    # Evidence inherits sub_agent from chain context.
    ev = next(p for n, p in cap.events if n == "evidence_added")
    assert ev["agent"] == "recon"


@pytest.mark.asyncio
async def test_set_chain_agent_persists_until_overridden() -> None:
    """Sequential phase transitions should overwrite without needing reset."""
    cap = _Capture()
    with event_emitter_scope(cap):
        set_chain_agent("recon", stage="research")
        emit_tool_call("a")
        set_chain_agent("quill", stage="documents")
        emit_tool_call("b")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    a = next(p for n, p in cap.events if n == "tool_call" and p["tool"] == "a")
    b = next(p for n, p in cap.events if n == "tool_call" and p["tool"] == "b")
    assert a["agent"] == "recon"
    assert b["agent"] == "quill"
    assert b["stage"] == "documents"
    # After the test, the contextvar still holds "quill" — that's fine
    # because each test gets its own asyncio task / context.
    assert get_current_chain_agent() == "quill"


@pytest.mark.asyncio
async def test_explicit_agent_kwarg_overrides_chain_context() -> None:
    cap = _Capture()
    with event_emitter_scope(cap), chain_agent_scope("recon"):
        emit_tool_call("x", agent="atlas")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    payload = cap.events[0][1]
    assert payload["agent"] == "atlas"
