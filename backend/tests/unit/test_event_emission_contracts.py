"""Event emission field contract tests — Rank 7.

Tests that all public emit helpers in ``ai_engine.agent_events`` produce
payloads that satisfy the field contract expected by
``_persist_generation_job_event``:

  Required top-level keys:  agent, status, message
  Optional but validated:   stage, tool, tier, source, latency_ms

All tests run fully synchronously — no DB connection, no running event loop
required.  The ``_fire`` helper degrades silently when no loop is running;
we capture payloads by binding a synchronous spy as the emitter.

Run with:
    pytest tests/unit/test_event_emission_contracts.py -v
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from ai_engine import agent_events
from ai_engine.agent_events import (
    emit_cache_hit,
    emit_evidence_added,
    emit_policy_decision,
    emit_tool_call,
    emit_tool_result,
    get_event_emitter,
    reset_event_emitter,
    set_event_emitter,
)
from ai_engine.agents.event_taxonomy import CANONICAL_EVENT_TYPES


# ── Test harness ──────────────────────────────────────────────────────────────

class _PayloadSpy:
    """Captures (event_name, payload) pairs synchronously via asyncio.run()."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    async def _async_emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        self.calls.append((event_name, payload))

    def reset(self) -> None:
        self.calls.clear()


def _run_with_spy(fn, *args, **kwargs) -> _PayloadSpy:
    """Run an async body that binds a spy, calls fn(), then drains the loop."""
    spy = _PayloadSpy()

    async def _run() -> None:
        token = set_event_emitter(spy._async_emit)
        try:
            fn(*args, **kwargs)
            # _fire schedules tasks; run a short tick to drain them.
            await asyncio.sleep(0)
        finally:
            reset_event_emitter(token)

    asyncio.run(_run())
    return spy


# ── Required field validator ──────────────────────────────────────────────────

_REQUIRED_PAYLOAD_KEYS = {"agent", "status", "message"}


def _assert_payload_contract(
    spy: _PayloadSpy,
    *,
    expected_event: Optional[str] = None,
    at_least_one: bool = True,
) -> Dict[str, Any]:
    """Assert the spy captured at least one call and the first payload is valid."""
    if at_least_one:
        assert spy.calls, "No events were emitted — check that the emitter binding works"
    event_name, payload = spy.calls[0]
    if expected_event:
        assert event_name == expected_event, (
            f"Expected event '{expected_event}', got '{event_name}'"
        )
    missing = _REQUIRED_PAYLOAD_KEYS - payload.keys()
    assert not missing, (
        f"Event '{event_name}' payload missing required keys: {missing}.  "
        f"Got: {list(payload.keys())}"
    )
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Test classes
# ─────────────────────────────────────────────────────────────────────────────

class TestEmitToolCall:
    """emit_tool_call() must produce a well-formed tool_call payload."""

    def test_basic_payload_has_required_keys(self) -> None:
        spy = _run_with_spy(emit_tool_call, "github.search", {"query": "python"}, agent="recon")
        payload = _assert_payload_contract(spy, expected_event="tool_call")
        assert payload["tool"] == "github.search"

    def test_agent_falls_back_to_pipeline_when_missing(self) -> None:
        spy = _run_with_spy(emit_tool_call, "test_tool")
        payload = _assert_payload_contract(spy)
        assert payload["agent"] == "pipeline"

    def test_status_is_running(self) -> None:
        spy = _run_with_spy(emit_tool_call, "test_tool", agent="recon")
        payload = _assert_payload_contract(spy)
        assert payload["status"] == "running"

    def test_event_name_is_canonical(self) -> None:
        spy = _run_with_spy(emit_tool_call, "any_tool", agent="recon")
        assert spy.calls
        event_name = spy.calls[0][0]
        assert event_name in CANONICAL_EVENT_TYPES, (
            f"Event '{event_name}' is not in CANONICAL_EVENT_TYPES"
        )

    def test_message_is_nonempty_string(self) -> None:
        spy = _run_with_spy(emit_tool_call, "my_tool", agent="recon")
        payload = _assert_payload_contract(spy)
        assert isinstance(payload["message"], str) and payload["message"]

    def test_arguments_preview_present_when_provided(self) -> None:
        spy = _run_with_spy(emit_tool_call, "my_tool", {"key": "val"}, agent="recon")
        payload = _assert_payload_contract(spy)
        assert "arguments_preview" in payload


class TestEmitToolResult:
    """emit_tool_result() must produce a well-formed tool_result payload."""

    def test_successful_result_status(self) -> None:
        spy = _run_with_spy(
            emit_tool_result, "github.search", {"count": 5},
            agent="recon", latency_ms=300, success=True
        )
        payload = _assert_payload_contract(spy, expected_event="tool_result")
        assert payload["status"] == "completed"

    def test_failed_result_status(self) -> None:
        spy = _run_with_spy(
            emit_tool_result, "github.search", None,
            agent="recon", success=False, error="Timeout"
        )
        payload = _assert_payload_contract(spy, expected_event="tool_result")
        assert payload["status"] == "failed"
        assert "error" in payload

    def test_latency_ms_stored_as_int(self) -> None:
        spy = _run_with_spy(
            emit_tool_result, "my_tool", {},
            agent="recon", latency_ms=450
        )
        payload = _assert_payload_contract(spy)
        assert isinstance(payload.get("latency_ms"), int)
        assert payload["latency_ms"] == 450

    def test_cache_hit_flag_present(self) -> None:
        spy = _run_with_spy(
            emit_tool_result, "my_tool", {},
            agent="recon", cache_hit=True
        )
        payload = _assert_payload_contract(spy)
        assert payload.get("cache_hit") is True

    def test_event_name_is_canonical(self) -> None:
        spy = _run_with_spy(emit_tool_result, "tool", {}, agent="recon")
        event_name = spy.calls[0][0]
        assert event_name in CANONICAL_EVENT_TYPES

    def test_omits_latency_when_not_provided(self) -> None:
        spy = _run_with_spy(emit_tool_result, "tool", {}, agent="recon")
        payload = _assert_payload_contract(spy)
        assert "latency_ms" not in payload


class TestEmitCacheHit:
    """emit_cache_hit() must produce a well-formed cache_hit payload."""

    def test_required_keys_present(self) -> None:
        spy = _run_with_spy(emit_cache_hit, "jd_cache", agent="recon", saved_ms=200)
        payload = _assert_payload_contract(spy, expected_event="cache_hit")
        assert "cache" in payload

    def test_saved_ms_included(self) -> None:
        spy = _run_with_spy(emit_cache_hit, "my_cache", agent="recon", saved_ms=500)
        payload = _assert_payload_contract(spy)
        assert payload.get("saved_ms") == 500

    def test_event_name_is_canonical(self) -> None:
        spy = _run_with_spy(emit_cache_hit, "my_cache", agent="recon")
        event_name = spy.calls[0][0]
        assert event_name in CANONICAL_EVENT_TYPES


class TestEmitEvidenceAdded:
    """emit_evidence_added() must produce a well-formed evidence_added payload."""

    def test_required_keys_present(self) -> None:
        spy = _run_with_spy(
            emit_evidence_added,
            tier="verbatim", source="profile", text="Python developer",
            sub_agent="recon"
        )
        payload = _assert_payload_contract(spy, expected_event="evidence_added")
        assert "tier" in payload and "source" in payload

    def test_tier_value_passed_through(self) -> None:
        spy = _run_with_spy(
            emit_evidence_added,
            tier="inferred", source="jd", text="leadership required",
            sub_agent="cipher"
        )
        payload = _assert_payload_contract(spy)
        assert payload["tier"] == "inferred"

    def test_snippet_is_truncated_to_160_chars(self) -> None:
        long_text = "x" * 300
        spy = _run_with_spy(
            emit_evidence_added,
            tier="verbatim", source="profile", text=long_text, sub_agent="recon"
        )
        payload = _assert_payload_contract(spy)
        assert len(payload.get("snippet", "")) <= 161  # 160 + possible ellipsis char

    def test_cross_confirmed_flag(self) -> None:
        spy = _run_with_spy(
            emit_evidence_added,
            tier="derived", source="tool", text="confirmed",
            sub_agent="recon", cross_confirmed=True
        )
        payload = _assert_payload_contract(spy)
        assert payload.get("cross_confirmed") is True

    def test_event_name_is_canonical(self) -> None:
        spy = _run_with_spy(
            emit_evidence_added, tier="verbatim", source="profile", text="x"
        )
        event_name = spy.calls[0][0]
        assert event_name in CANONICAL_EVENT_TYPES


class TestEmitPolicyDecision:
    """emit_policy_decision() must produce a well-formed policy_decision payload."""

    def test_required_keys_present(self) -> None:
        spy = _run_with_spy(
            emit_policy_decision,
            "retry", reason="Confidence below threshold", agent="sentinel"
        )
        payload = _assert_payload_contract(spy, expected_event="policy_decision")
        assert "decision" in payload

    def test_decision_value_passed_through(self) -> None:
        spy = _run_with_spy(
            emit_policy_decision,
            "skip_module", reason="Module disabled", agent="quill"
        )
        payload = _assert_payload_contract(spy)
        assert payload["decision"] == "skip_module"

    def test_reason_truncated_to_240(self) -> None:
        long_reason = "r" * 500
        spy = _run_with_spy(
            emit_policy_decision,
            "skip", reason=long_reason, agent="pipeline"
        )
        payload = _assert_payload_contract(spy)
        # _truncate adds ellipsis char so effective len <= 240
        assert len(payload.get("reason", "")) <= 241

    def test_event_name_is_canonical(self) -> None:
        spy = _run_with_spy(
            emit_policy_decision, "skip", reason="n/a", agent="pipeline"
        )
        event_name = spy.calls[0][0]
        assert event_name in CANONICAL_EVENT_TYPES


class TestNoEmitterSilence:
    """With no emitter bound, all emit helpers must be completely silent."""

    def test_tool_call_no_emitter_does_not_raise(self) -> None:
        # Reset is guaranteed by the context var default=None path
        token = set_event_emitter(None)
        try:
            emit_tool_call("tool", agent="recon")  # must not raise
        finally:
            reset_event_emitter(token)

    def test_tool_result_no_emitter_does_not_raise(self) -> None:
        token = set_event_emitter(None)
        try:
            emit_tool_result("tool", {}, agent="recon")
        finally:
            reset_event_emitter(token)

    def test_cache_hit_no_emitter_does_not_raise(self) -> None:
        token = set_event_emitter(None)
        try:
            emit_cache_hit("cache", agent="recon")
        finally:
            reset_event_emitter(token)

    def test_evidence_added_no_emitter_does_not_raise(self) -> None:
        token = set_event_emitter(None)
        try:
            emit_evidence_added(tier="verbatim", source="profile", text="x")
        finally:
            reset_event_emitter(token)
