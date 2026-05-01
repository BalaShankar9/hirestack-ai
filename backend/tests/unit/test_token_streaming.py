"""S14-F3: token streaming infrastructure tests.

Pins the contract for `AIClient.stream_completion`, `EventSink.emit_token_delta`,
and the `STREAMING_TOKENS_ENABLED` kill switch. Drafter + optimizer wiring +
frontend hook ship in follow-up commits; this slice is pure infrastructure so
those changes land behind a verified contract.
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_engine.agents.event_taxonomy import (
    PIPELINE_LIFECYCLE_EVENTS,
    TOKEN_DELTA,
    streaming_tokens_enabled,
)
from app.services.pipeline_runtime import (
    PIPELINE_EVENT_SCHEMA_VERSION,
    CollectorSink,
    DatabaseSink,
    NullSink,
    SSESink,
    _ExecutionPathTaggingSink,
)


# ─── event_taxonomy ────────────────────────────────────────────────────


def test_token_delta_in_canonical_taxonomy():
    assert TOKEN_DELTA == "token_delta"
    assert TOKEN_DELTA in PIPELINE_LIFECYCLE_EVENTS


def test_streaming_tokens_env_switch(monkeypatch):
    monkeypatch.delenv("STREAMING_TOKENS_ENABLED", raising=False)
    assert streaming_tokens_enabled() is False
    for v in ("1", "true", "yes", "on", "TRUE"):
        monkeypatch.setenv("STREAMING_TOKENS_ENABLED", v)
        assert streaming_tokens_enabled() is True, v
    monkeypatch.setenv("STREAMING_TOKENS_ENABLED", "0")
    assert streaming_tokens_enabled() is False


# ─── EventSink.emit_token_delta ────────────────────────────────────────


@pytest.mark.asyncio
async def test_collector_sink_records_token_delta_via_default_emit():
    sink = CollectorSink()
    await sink.emit_token_delta(
        stage="drafter", document_kind="cv", delta="Hello ", sequence=0,
    )
    await sink.emit_token_delta(
        stage="drafter", document_kind="cv", delta="world", sequence=1,
    )
    assert len(sink.events) == 2
    assert sink.events[0].event_type == "token_delta"
    assert sink.events[0].data["delta"] == "Hello "
    assert sink.events[0].data["sequence"] == 0
    assert sink.events[1].data["sequence"] == 1


@pytest.mark.asyncio
async def test_database_sink_drops_token_delta():
    """Token deltas must NEVER hit generation_job_events."""
    mock_db = MagicMock()
    sink = DatabaseSink(
        db=mock_db, tables={"events": "e", "jobs": "j"},
        job_id="j1", user_id="u1", application_id="a1",
    )
    await sink.emit_token_delta(
        stage="drafter", document_kind="cv", delta="x", sequence=0,
    )
    # No DB calls of any kind triggered.
    assert mock_db.method_calls == []


@pytest.mark.asyncio
async def test_sse_sink_emits_token_delta_frame():
    sink = SSESink(maxsize=16)
    await sink.emit_token_delta(
        stage="drafter", document_kind="cover_letter", delta="Dear ", sequence=0,
    )
    raw = await sink.queue.get()
    assert raw.startswith("event: token_delta\n")
    payload = json.loads(raw.split("\n")[1].replace("data: ", ""))
    assert payload["schema_version"] == PIPELINE_EVENT_SCHEMA_VERSION
    assert payload["stage"] == "drafter"
    assert payload["document_kind"] == "cover_letter"
    assert payload["delta"] == "Dear "
    assert payload["sequence"] == 0


@pytest.mark.asyncio
async def test_sse_sink_token_deltas_are_not_coalesced_by_sequence():
    """Distinct sequence numbers must each survive the coalescing queue."""
    sink = SSESink(maxsize=64)
    for i in range(5):
        await sink.emit_token_delta(
            stage="drafter", document_kind="cv", delta=f"chunk{i} ", sequence=i,
        )
    assert sink.queue.qsize() == 5
    deltas = []
    for _ in range(5):
        raw = sink.queue.get_nowait()
        deltas.append(json.loads(raw.split("\n")[1].replace("data: ", ""))["delta"])
    assert deltas == [f"chunk{i} " for i in range(5)]


@pytest.mark.asyncio
async def test_token_deltas_droppable_under_extreme_pressure():
    """Token deltas are non-terminal — they may be dropped when terminal
    events need queue room. Verifies the safety property: pipeline never
    stalls on token backpressure.
    """
    sink = SSESink(maxsize=4)
    for i in range(10):
        await sink.emit_token_delta(
            stage="drafter", document_kind="cv", delta="x", sequence=i,
        )
    # Bounded.
    assert sink.queue.qsize() <= 4
    assert sink.queue.dropped > 0


@pytest.mark.asyncio
async def test_execution_path_tagging_sink_forwards_token_delta():
    inner = CollectorSink()
    runtime = MagicMock()
    runtime._execution_path = "agent"
    wrapper = _ExecutionPathTaggingSink(inner, runtime)
    await wrapper.emit_token_delta(
        stage="optimizer", document_kind="cv", delta="z", sequence=0,
    )
    assert len(inner.events) == 1
    assert inner.events[0].event_type == "token_delta"


@pytest.mark.asyncio
async def test_null_sink_swallows_token_delta():
    sink = NullSink()
    await sink.emit_token_delta(
        stage="drafter", document_kind="cv", delta="x", sequence=0,
    )  # must not raise


# ─── AIClient.stream_completion ────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_completion_yields_chunks_and_tracks_usage(monkeypatch):
    """Validate the AIClient facade contract WITHOUT calling Gemini.

    We monkeypatch _provider.stream_completion with a controlled async
    generator and assert: (a) all chunks bubble through, (b) usage is
    tracked once on completion, (c) cache is bypassed.
    """
    from ai_engine.client import AIClient

    client = AIClient()

    async def fake_stream(**kwargs):
        for tok in ["Hello ", "world", "!"]:
            yield tok

    monkeypatch.setattr(client._provider, "stream_completion", fake_stream)

    chunks = []
    async for c in client.stream_completion(
        prompt="say hi", task_type="drafting", temperature=0.1,
    ):
        chunks.append(c)

    assert chunks == ["Hello ", "world", "!"]
    # Usage tracked once for the full text.
    assert client.token_usage["call_count"] == 1
    assert client.token_usage["completion_tokens"] >= 1


@pytest.mark.asyncio
async def test_stream_completion_propagates_exceptions(monkeypatch):
    from ai_engine.client import AIClient

    client = AIClient()

    async def fake_stream(**kwargs):
        yield "partial"
        raise RuntimeError("provider exploded mid-stream")

    monkeypatch.setattr(client._provider, "stream_completion", fake_stream)

    chunks = []
    with pytest.raises(RuntimeError, match="provider exploded"):
        async for c in client.stream_completion(prompt="hi"):
            chunks.append(c)
    # Caller saw the partial chunk before the exception.
    assert chunks == ["partial"]


@pytest.mark.asyncio
async def test_stream_completion_bypasses_cache(monkeypatch):
    """Token streaming MUST NOT hit the cache (partial responses uncacheable)."""
    from ai_engine.client import AIClient
    from ai_engine import cache as cache_mod

    client = AIClient()

    async def fake_stream(**kwargs):
        yield "fresh"

    monkeypatch.setattr(client._provider, "stream_completion", fake_stream)

    fake_cache = MagicMock()
    fake_cache.get = MagicMock(return_value="CACHED")
    fake_cache.put = MagicMock()
    monkeypatch.setattr(cache_mod, "get_ai_cache", lambda: fake_cache)

    chunks = [c async for c in client.stream_completion(prompt="hi")]
    assert chunks == ["fresh"]
    # Neither cache.get nor cache.put may be called.
    assert fake_cache.get.call_count == 0
    assert fake_cache.put.call_count == 0
