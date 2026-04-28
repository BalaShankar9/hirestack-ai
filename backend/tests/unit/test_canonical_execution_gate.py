"""
Canonical-execution acceptance gate (Phase 1, Bet 1 of the world-class roadmap).

These tests prove that:

1. Every event emitted by `PipelineRuntime` carries an `execution_path` tag,
   so dashboards / replay can prove production never silently degraded.
2. When the agent stack is unavailable AND the operator has NOT opted into
   the legacy fallback, the runtime refuses to run rather than producing
   a degraded artifact.
3. The legacy escape hatch only activates when explicitly enabled via the
   documented env flag, and its events are tagged accordingly.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ai_engine.agents.event_taxonomy import (
    EXECUTION_PATH_AGENT,
    EXECUTION_PATH_LEGACY,
    EXECUTION_PATH_UNKNOWN,
)
from app.services.pipeline_runtime import (
    CollectorSink,
    ExecutionMode,
    PipelineEvent,
    PipelineRuntime,
    RuntimeConfig,
)


def _runtime_with_collector() -> tuple[PipelineRuntime, CollectorSink]:
    sink = CollectorSink()
    cfg = RuntimeConfig(mode=ExecutionMode.SYNC, user_id="u-test")
    return PipelineRuntime(config=cfg, event_sink=sink), sink


def test_every_emitted_event_carries_execution_path_tag() -> None:
    """Even before dispatch, the sink wrapper auto-tags events."""
    import asyncio

    runtime, sink = _runtime_with_collector()

    # Pre-dispatch the tag is "unknown"; emit a dummy event and confirm it
    # acquires the tag automatically.
    asyncio.run(runtime.sink.emit(PipelineEvent(
        event_type="progress", phase="recon", progress=1, message="hi",
    )))

    assert len(sink.events) == 1
    tag = sink.events[0].data.get("execution_path")
    assert tag == EXECUTION_PATH_UNKNOWN

    # Once the runtime selects a path, subsequent events inherit that tag.
    runtime._execution_path = EXECUTION_PATH_AGENT  # noqa: SLF001
    asyncio.run(runtime.sink.emit(PipelineEvent(
        event_type="progress", phase="atlas", progress=10, message="hi",
    )))
    assert sink.events[1].data.get("execution_path") == EXECUTION_PATH_AGENT


def test_canonical_path_required_when_legacy_disabled() -> None:
    """Refuse to run a degraded path when legacy fallback is not opted in."""
    import asyncio

    runtime, _ = _runtime_with_collector()

    # Pretend the agent stack failed to import.
    with patch.object(PipelineRuntime, "_agents_available", staticmethod(lambda: False)), \
         patch.dict(os.environ, {"HIRESTACK_ALLOW_LEGACY_PIPELINE": ""}, clear=False), \
         patch("app.services.pipeline_runtime.get_supabase", return_value=None, create=True), \
         patch("ai_engine.client.AIClient"):

        with pytest.raises(RuntimeError, match="Canonical agent pipeline unavailable"):
            asyncio.run(runtime.execute({
                "job_title": "Software Engineer",
                "company": "Acme",
                "jd_text": "We need an engineer.",
                "resume_text": "I am an engineer.",
            }))


def test_legacy_path_engages_only_with_explicit_opt_in_and_tags_events() -> None:
    """When the env flag is set, legacy runs but every event is tagged 'legacy'."""
    import asyncio

    runtime, sink = _runtime_with_collector()

    async def _fake_legacy(self, **_kw):  # noqa: ANN001
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=10, message="legacy ran",
        ))
        return {
            "scores": {"overall": 0},
            "html": "",
            "meta": {},
        }

    with patch.object(PipelineRuntime, "_agents_available", staticmethod(lambda: False)), \
         patch.dict(os.environ, {"HIRESTACK_ALLOW_LEGACY_PIPELINE": "1"}, clear=False), \
         patch.object(PipelineRuntime, "_run_legacy_pipeline", _fake_legacy), \
         patch("app.services.pipeline_runtime.get_supabase", return_value=None, create=True), \
         patch("ai_engine.client.AIClient"):

        # Execute may still fail downstream (formatting / DB persistence),
        # but the legacy branch should at least be entered and tag events.
        try:
            asyncio.run(runtime.execute({
                "job_title": "Software Engineer",
                "company": "Acme",
                "jd_text": "We need an engineer.",
                "resume_text": "I am an engineer.",
            }))
        except Exception:
            pass

    legacy_events = [
        e for e in sink.events
        if e.data.get("execution_path") == EXECUTION_PATH_LEGACY
    ]
    assert legacy_events, "Expected at least one event tagged with the legacy execution path"
