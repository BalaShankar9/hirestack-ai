"""Verify AIClient.complete_json publishes enriched agent events.

Phase A.3 of the Agent World-Class plan: every chain's AI call should
automatically surface as `tool_call` / `tool_result` (with cache_hit
tagging and policy_decision on cascade failover) on the event stream
without per-chain instrumentation.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_engine.agent_events import (
    chain_agent_scope,
    event_emitter_scope,
)


class _Capture:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, payload))


@pytest.mark.asyncio
async def test_complete_json_emits_tool_call_and_result_on_success() -> None:
    cap = _Capture()
    with patch("ai_engine.client.settings") as mock_settings:
        mock_settings.gemini_model = "default-model"
        mock_settings.gemini_max_tokens = 8192
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_use_vertexai = False
        mock_settings.ai_max_input_tokens = 100_000
        mock_settings.daily_token_budget = 10_000_000

        from ai_engine.client import AIClient

        client = AIClient()
        # Bypass cache + provider wiring.
        client._provider = MagicMock()
        client._provider.complete_json = AsyncMock(return_value={"ok": True, "items": [1, 2]})
        # Bypass budget + truncation that depend on settings internals.
        client._check_budget = MagicMock(return_value=None)
        client._truncate_input = MagicMock(side_effect=lambda t, **_: t)
        client._track_usage = MagicMock(return_value=None)

        # Prevent cache from short-circuiting.
        with patch("ai_engine.cache.get_ai_cache") as mock_cache:
            mock_cache.return_value = MagicMock(get=MagicMock(return_value=None), put=MagicMock())

            with event_emitter_scope(cap), chain_agent_scope("recon", stage="research"):
                result = await client.complete_json(
                    prompt="hello", system="sys",
                    task_type="reasoning", temperature=0.2,
                )

        # Drain any scheduled background emit tasks.
        for _ in range(5):
            await asyncio.sleep(0)

    assert result == {"ok": True, "items": [1, 2]}
    names = [n for n, _ in cap.events]
    assert "tool_call" in names
    assert "tool_result" in names

    call = next(p for n, p in cap.events if n == "tool_call")
    assert call["tool"] == "ai.reasoning"
    assert call["agent"] == "recon"
    assert call["stage"] == "research"

    res = next(p for n, p in cap.events if n == "tool_result")
    assert res["status"] == "completed"
    assert res["cache_hit"] is False
    assert res["agent"] == "recon"
    assert isinstance(res["latency_ms"], int)


@pytest.mark.asyncio
async def test_complete_json_emits_cache_hit_when_served_from_cache() -> None:
    cap = _Capture()
    with patch("ai_engine.client.settings") as mock_settings:
        mock_settings.gemini_model = "default-model"
        mock_settings.gemini_max_tokens = 8192
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_use_vertexai = False
        mock_settings.ai_max_input_tokens = 100_000
        mock_settings.daily_token_budget = 10_000_000

        from ai_engine.client import AIClient

        client = AIClient()
        client._provider = MagicMock()
        client._provider.complete_json = AsyncMock()  # Should NOT be called.
        client._check_budget = MagicMock(return_value=None)
        client._truncate_input = MagicMock(side_effect=lambda t, **_: t)
        client._track_usage = MagicMock(return_value=None)

        cached_value = {"cached": True, "k": "v"}
        with patch("ai_engine.cache.get_ai_cache") as mock_cache:
            mock_cache.return_value = MagicMock(
                get=MagicMock(return_value=cached_value),
                put=MagicMock(),
            )

            with event_emitter_scope(cap), chain_agent_scope("quill"):
                result = await client.complete_json(
                    prompt="hi", task_type="drafting",
                )

        for _ in range(5):
            await asyncio.sleep(0)

    assert result == cached_value
    client._provider.complete_json.assert_not_called()

    res = next(p for n, p in cap.events if n == "tool_result")
    assert res["cache_hit"] is True
    assert res["agent"] == "quill"
    assert res["tool"] == "ai.drafting"


@pytest.mark.asyncio
async def test_complete_json_emits_policy_decision_on_cascade_failover() -> None:
    cap = _Capture()
    with patch("ai_engine.client.settings") as mock_settings:
        mock_settings.gemini_model = "default-model"
        mock_settings.gemini_max_tokens = 8192
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_use_vertexai = False
        mock_settings.ai_max_input_tokens = 100_000
        mock_settings.daily_token_budget = 10_000_000

        from ai_engine.client import AIClient

        client = AIClient()
        client._provider = MagicMock()
        # First model raises, second succeeds.
        client._provider.complete_json = AsyncMock(
            side_effect=[
                RuntimeError("transient upstream failure"),
                {"ok": True},
            ]
        )
        # Force a 2-model cascade for any task_type.
        client._resolve_cascade = MagicMock(return_value=["model-a", "model-b"])
        client._check_budget = MagicMock(return_value=None)
        client._truncate_input = MagicMock(side_effect=lambda t, **_: t)
        client._track_usage = MagicMock(return_value=None)

        with patch("ai_engine.cache.get_ai_cache") as mock_cache:
            mock_cache.return_value = MagicMock(
                get=MagicMock(return_value=None),
                put=MagicMock(),
            )

            with event_emitter_scope(cap), chain_agent_scope("cipher"):
                result = await client.complete_json(prompt="x", task_type="reasoning")

        for _ in range(5):
            await asyncio.sleep(0)

    assert result == {"ok": True}
    names = [n for n, _ in cap.events]
    assert "policy_decision" in names

    pd = next(p for n, p in cap.events if n == "policy_decision")
    assert pd["decision"] == "model_cascade_failover"
    assert pd["metadata"]["failed"] == "model-a"
    assert pd["metadata"]["next"] == "model-b"
    # And the eventual tool_result is success.
    success = [p for n, p in cap.events if n == "tool_result" and p["status"] == "completed"]
    assert len(success) == 1
