"""PR m6-pr23: AIClient.complete_json wraps each LLM attempt in trace_llm.

We don't need the real Langfuse SDK — we monkeypatch
``ai_engine.observability.trace_llm`` to a recording async ctx manager
and assert it's called with the expected metadata.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _RecordingTracer:
    """Drop-in stub for ``trace_llm`` async context manager."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @asynccontextmanager
    async def __call__(self, **kwargs: Any):
        self.calls.append(kwargs)
        # Yield a span-shaped object so the wrap-site .update() works.
        span = MagicMock()
        span.update = MagicMock()
        yield span


def _stub_settings(mock_settings) -> None:
    mock_settings.gemini_model = "default-model"
    mock_settings.gemini_max_tokens = 8192
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_use_vertexai = False
    mock_settings.ai_max_input_tokens = 100_000
    mock_settings.daily_token_budget = 10_000_000


@pytest.mark.asyncio
async def test_complete_json_wraps_cascade_attempt_in_trace_llm() -> None:
    tracer = _RecordingTracer()

    with patch("ai_engine.client.settings") as mock_settings, \
         patch("ai_engine.observability.trace_llm", tracer):
        _stub_settings(mock_settings)

        from ai_engine.client import AIClient
        client = AIClient()
        client._provider = MagicMock()
        client._provider.complete_json = AsyncMock(return_value={"ok": True})
        client._check_budget = MagicMock(return_value=None)
        client._truncate_input = MagicMock(side_effect=lambda t, **_: t)
        client._track_usage = MagicMock(return_value=None)
        # Force a single-model cascade for determinism.
        client._resolve_cascade = MagicMock(return_value=["gemini-2.5-pro"])

        with patch("ai_engine.cache.get_ai_cache") as mock_cache:
            mock_cache.return_value = MagicMock(
                get=MagicMock(return_value=None), put=MagicMock(),
            )
            result = await client.complete_json(
                prompt="hello world", system="sys",
                task_type="planning", temperature=0.2,
            )

    assert result == {"ok": True}
    # Exactly one tracer entry for the single attempt.
    assert len(tracer.calls) == 1
    call = tracer.calls[0]
    assert call["model"] == "gemini-2.5-pro"
    assert call["name"] == "ai.planning"
    md = call["metadata"]
    assert md["task_type"] == "planning"
    assert md["attempt"] == 1
    assert md["max_attempts"] == 1
    assert md["temperature"] == 0.2
    inp = call["input"]
    assert inp["system"] == "sys"
    assert inp["prompt"].startswith("hello world")


@pytest.mark.asyncio
async def test_complete_json_traces_each_cascade_attempt_on_failover() -> None:
    """First model raises → tracer called twice with attempt=1 then attempt=2."""
    tracer = _RecordingTracer()

    with patch("ai_engine.client.settings") as mock_settings, \
         patch("ai_engine.observability.trace_llm", tracer):
        _stub_settings(mock_settings)

        from ai_engine.client import AIClient
        client = AIClient()
        client._provider = MagicMock()
        # First call raises generic error → cascade falls to next model.
        client._provider.complete_json = AsyncMock(
            side_effect=[RuntimeError("transient"), {"ok": True}],
        )
        client._check_budget = MagicMock(return_value=None)
        client._truncate_input = MagicMock(side_effect=lambda t, **_: t)
        client._track_usage = MagicMock(return_value=None)
        client._resolve_cascade = MagicMock(
            return_value=["gemini-2.5-pro", "gemini-2.5-flash"],
        )

        with patch("ai_engine.cache.get_ai_cache") as mock_cache:
            mock_cache.return_value = MagicMock(
                get=MagicMock(return_value=None), put=MagicMock(),
            )
            result = await client.complete_json(
                prompt="x", system=None,
                task_type="reasoning", temperature=0.5,
            )

    assert result == {"ok": True}
    assert len(tracer.calls) == 2
    # attempt order preserved
    assert tracer.calls[0]["model"] == "gemini-2.5-pro"
    assert tracer.calls[0]["metadata"]["attempt"] == 1
    assert tracer.calls[1]["model"] == "gemini-2.5-flash"
    assert tracer.calls[1]["metadata"]["attempt"] == 2
