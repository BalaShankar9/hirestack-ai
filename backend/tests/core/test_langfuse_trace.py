"""PR m6-pr23: Langfuse trace_llm enhancements.

Validates the input-payload acceptance, trace_id contextvar publication,
and exception-on-error behaviour. Uses a fake Langfuse client so we don't
need real API keys or network.
"""
from __future__ import annotations

from typing import Any

import pytest


class _FakeSpan:
    """Mimics the subset of Langfuse Span API trace_llm uses."""

    def __init__(self, name: str, metadata: dict, trace_id: str, input: Any = None):
        self.name = name
        self.metadata = metadata
        self.trace_id = trace_id
        self.input = input
        self.updates: list[dict] = []
        self.ended = False

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def end(self) -> None:
        self.ended = True


class _FakeLangfuse:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []
        self._counter = 0

    def span(self, *, name: str, metadata: dict, input: Any = None) -> _FakeSpan:
        self._counter += 1
        sp = _FakeSpan(name, metadata, trace_id=f"trace-{self._counter}", input=input)
        self.spans.append(sp)
        return sp


@pytest.fixture
def fake_langfuse(monkeypatch):
    """Inject a fake Langfuse client into the wrapper's memo."""
    import ai_engine.observability.langfuse_client as m

    fake = _FakeLangfuse()
    monkeypatch.setattr(m, "_client", fake)
    monkeypatch.setattr(m, "_init_attempted", True)
    yield fake
    # Reset for other tests in the run.
    monkeypatch.setattr(m, "_client", None)
    monkeypatch.setattr(m, "_init_attempted", False)


@pytest.mark.asyncio
async def test_trace_llm_publishes_trace_id_to_contextvar(fake_langfuse):
    from ai_engine.observability import get_current_trace_id, trace_llm

    # Outside the ctx, no trace id.
    assert get_current_trace_id() is None

    captured: list[str | None] = []
    async with trace_llm(model="gemini-2.5-pro", name="ai.test") as span:
        captured.append(get_current_trace_id())
        assert span is not None
        assert span.metadata["model"] == "gemini-2.5-pro"

    # After exit, contextvar reset.
    assert get_current_trace_id() is None
    # During the ctx we saw a non-None trace id.
    assert captured[0] == "trace-1"


@pytest.mark.asyncio
async def test_trace_llm_passes_input_payload(fake_langfuse):
    from ai_engine.observability import trace_llm

    payload = {"system": "you are helpful", "prompt": "summarise X"}
    async with trace_llm(
        model="gemini-2.5-flash",
        name="ai.summarise",
        metadata={"task_type": "summary"},
        input=payload,
    ) as span:
        assert span is not None

    sp = fake_langfuse.spans[0]
    assert sp.input == payload
    assert sp.metadata["task_type"] == "summary"
    assert sp.ended is True


@pytest.mark.asyncio
async def test_trace_llm_records_error_level_on_exception(fake_langfuse):
    from ai_engine.observability import trace_llm

    with pytest.raises(RuntimeError, match="boom"):
        async with trace_llm(model="x", name="ai.bad"):
            raise RuntimeError("boom")

    sp = fake_langfuse.spans[0]
    assert sp.ended is True
    # Last update should carry ERROR level.
    levels = [u.get("level") for u in sp.updates]
    assert "ERROR" in levels


@pytest.mark.asyncio
async def test_get_current_trace_id_is_none_when_disabled():
    """No client → contextvar stays None even inside the ctx."""
    from ai_engine.observability import get_current_trace_id, trace_llm

    # Make sure no client is memoised from a prior test.
    import ai_engine.observability.langfuse_client as m
    m._client = None
    m._init_attempted = True  # short-circuit re-init

    async with trace_llm(model="m") as span:
        assert span is None
        assert get_current_trace_id() is None
