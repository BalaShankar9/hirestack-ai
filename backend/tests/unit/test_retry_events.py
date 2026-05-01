"""S14-F5: retry events.

Pins:
- ``EventSink.emit_retry`` default funnels into a ``retry`` PipelineEvent.
- SSESink serialises ``retry`` frames with the right wire format.
- ``_run_with_token_sink`` binds a per-Task retry emitter into the contextvar.
- AIClient.tenacity ``before_sleep`` hook publishes a retry event when an
  emitter is bound (and is silent otherwise).
- Routed-model fallback publishes a retry event with model + next_model.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.services.pipeline_runtime import (
    CollectorSink,
    SSESink,
    get_retry_emitter,
    reset_retry_emitter,
    set_retry_emitter,
)


# ─── EventSink.emit_retry default routing ──────────────────────────


@pytest.mark.asyncio
async def test_collector_sink_emit_retry_funnels_to_emit():
    sink = CollectorSink()
    await sink.emit_retry(
        stage="quill", attempt=2, max_attempts=6,
        reason="429 rate limit", model="gemini-1.5-pro",
        wait_ms=4_000,
    )
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.event_type == "retry"
    assert ev.stage == "quill"
    assert ev.data["attempt"] == 2
    assert ev.data["max_attempts"] == 6
    assert ev.data["model"] == "gemini-1.5-pro"
    assert ev.data["wait_ms"] == 4_000
    assert "429" in ev.data["reason"]


@pytest.mark.asyncio
async def test_collector_sink_emit_retry_carries_next_model_for_cascade():
    sink = CollectorSink()
    await sink.emit_retry(
        stage="forge", attempt=1, max_attempts=2,
        reason="quota_exhausted", model="gemini-2.0-flash",
        next_model="gemini-1.5-flash",
    )
    ev = sink.events[0]
    assert ev.data["next_model"] == "gemini-1.5-flash"


@pytest.mark.asyncio
async def test_sse_sink_serialises_retry_frame():
    sink = SSESink()
    await sink.emit_retry(
        stage="forge", attempt=3, max_attempts=6,
        reason="server overloaded", model="gemini-2.0-flash",
        wait_ms=8_000,
    )
    await sink.close()
    frames: List[str] = []
    async for chunk in sink.iter_events():
        frames.append(chunk)
    assert any("event: retry" in f for f in frames)
    assert any('"attempt": 3' in f for f in frames)
    assert any('"model": "gemini-2.0-flash"' in f for f in frames)


# ─── Retry emitter contextvar isolation ────────────────────────────


@pytest.mark.asyncio
async def test_retry_emitter_isolated_across_tasks():
    captured_a: List[int] = []
    captured_b: List[int] = []

    async def emitter_a(attempt, max_attempts, reason, **kw):
        captured_a.append(attempt)

    async def emitter_b(attempt, max_attempts, reason, **kw):
        captured_b.append(attempt * 10)

    async def task_a():
        tok = set_retry_emitter(emitter_a)
        try:
            assert get_retry_emitter() is emitter_a
            await get_retry_emitter()(attempt=1, max_attempts=6, reason="x")
        finally:
            reset_retry_emitter(tok)

    async def task_b():
        tok = set_retry_emitter(emitter_b)
        try:
            assert get_retry_emitter() is emitter_b
            await get_retry_emitter()(attempt=2, max_attempts=6, reason="y")
        finally:
            reset_retry_emitter(tok)

    await asyncio.gather(task_a(), task_b())
    assert captured_a == [1]
    assert captured_b == [20]


# ─── tenacity before_sleep hook ────────────────────────────────────


@pytest.mark.asyncio
async def test_before_sleep_hook_emits_retry_event_when_emitter_bound():
    """Synthesise a fake tenacity RetryCallState and invoke the hook."""
    from ai_engine.client import _retry_event_before_sleep

    captured: List[Dict[str, Any]] = []

    async def emitter(attempt, max_attempts, reason, **kw):
        captured.append({
            "attempt": attempt, "max_attempts": max_attempts,
            "reason": reason, "wait_ms": kw.get("wait_ms"),
        })

    # Build a minimal RetryCallState shim (only the attrs the hook reads).
    rs = MagicMock()
    outcome = MagicMock()
    outcome.failed = True
    outcome.exception.return_value = RuntimeError("429 RESOURCE_EXHAUSTED")
    rs.outcome = outcome
    rs.attempt_number = 3
    rs.next_action = MagicMock()
    rs.next_action.sleep = 4.0  # seconds
    rs.fn = MagicMock()  # _RETRY_LOG_FALLBACK touches this

    tok = set_retry_emitter(emitter)
    try:
        _retry_event_before_sleep(rs)
        # Yield once so the scheduled task runs.
        await asyncio.sleep(0)
    finally:
        reset_retry_emitter(tok)

    assert len(captured) == 1
    assert captured[0]["attempt"] == 3
    assert captured[0]["max_attempts"] == 6
    assert captured[0]["wait_ms"] == 4_000
    assert "429" in captured[0]["reason"]


@pytest.mark.asyncio
async def test_before_sleep_hook_silent_when_no_emitter():
    from ai_engine.client import _retry_event_before_sleep

    rs = MagicMock()
    outcome = MagicMock()
    outcome.failed = True
    outcome.exception.return_value = RuntimeError("transient")
    rs.outcome = outcome
    rs.attempt_number = 1
    rs.next_action = MagicMock()
    rs.next_action.sleep = 1.0
    rs.fn = MagicMock()

    # No emitter bound; must not raise.
    assert get_retry_emitter() is None
    _retry_event_before_sleep(rs)
    await asyncio.sleep(0)


# ─── Routed-model fallback emits cascade retry ─────────────────────


@pytest.mark.asyncio
async def test_routed_model_fallback_emits_cascade_retry_event():
    """Force a quota-exhausted exception on the routed model and verify the
    fallback path publishes a retry event with model + next_model.
    """
    from ai_engine.client import _GeminiProvider

    captured: List[Dict[str, Any]] = []

    async def emitter(attempt, max_attempts, reason, **kw):
        captured.append({
            "attempt": attempt, "reason": reason,
            "model": kw.get("model"), "next_model": kw.get("next_model"),
        })

    provider = _GeminiProvider()
    provider.model_name = "gemini-fallback"
    # Bypass throttle lock init.
    provider._throttle_lock = asyncio.Lock()

    # Track call sequence: first call (routed model) raises quota error,
    # second call (fallback model) succeeds.
    call_log = {"n": 0}

    def _fake_generate(*, model, contents, config):
        call_log["n"] += 1
        if call_log["n"] == 1:
            # Must match _is_quota_exhausted's lookup table.
            raise RuntimeError("insufficient_quota: routed model out of capacity")
        ok = MagicMock()
        ok.text = "{}"
        return ok

    fake_models = MagicMock()
    fake_models.generate_content.side_effect = _fake_generate
    fake_client = MagicMock()
    fake_client.models = fake_models

    # Stub circuit breaker as a no-op async ctxmgr so the inner call goes through.
    class _NoopBreaker:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    tok = set_retry_emitter(emitter)
    try:
        with patch.object(provider, "_get_client", return_value=fake_client), \
             patch("ai_engine.client._get_model_breaker", return_value=_NoopBreaker()):
            await provider._generate_content_throttled(
                contents="hi", config=MagicMock(), model="gemini-routed",
            )
    finally:
        reset_retry_emitter(tok)

    assert call_log["n"] == 2  # routed failed → fallback called
    assert len(captured) == 1
    assert captured[0]["model"] == "gemini-routed"
    assert captured[0]["next_model"] == "gemini-fallback"
    assert "quota_exhausted" in captured[0]["reason"]


# ─── pipeline_runtime binds retry emitter ──────────────────────────


@pytest.mark.asyncio
async def test_runtime_helper_binding_pattern_routes_through_sink():
    """Smoke-test the wiring pattern used by ``_run_with_token_sink``:
    bind a per-Task retry emitter that funnels into a CollectorSink and
    verify a downstream caller (e.g. the AIClient before_sleep hook) can
    fetch it via ``get_retry_emitter()`` and publish a retry event.
    """
    sink = CollectorSink()

    async def _retry(attempt, max_attempts, reason, **kw):
        await sink.emit_retry(
            stage="quill", attempt=attempt, max_attempts=max_attempts,
            reason=reason, **kw,
        )

    captured_emitter: List[Optional[Any]] = []

    async def fake_pipeline_body():
        emitter = get_retry_emitter()
        captured_emitter.append(emitter)
        if emitter is not None:
            await emitter(attempt=2, max_attempts=6, reason="probe")

    tok = set_retry_emitter(_retry)
    try:
        await fake_pipeline_body()
    finally:
        reset_retry_emitter(tok)

    assert captured_emitter[0] is not None
    retry_events = [e for e in sink.events if e.event_type == "retry"]
    assert len(retry_events) == 1
    assert retry_events[0].data["attempt"] == 2
    assert retry_events[0].stage == "quill"
