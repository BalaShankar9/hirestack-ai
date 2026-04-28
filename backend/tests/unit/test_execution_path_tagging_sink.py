"""S3-F1 — Behavioral tests for the dual-sink wrapping invariants.

`PipelineRuntime` always wraps the user-supplied sink in
`_ExecutionPathTaggingSink`. Production dashboards trust the
`execution_path` tag on every event to detect degraded paths. The
wrapper also forwards attribute access transparently so callers that
hold a `CollectorSink` / `SSESink` reference can keep introspecting
through `runtime.sink.events` / `runtime.sink.iter_events`.

These invariants are not allowed to drift; this test pins them.
"""
from __future__ import annotations

import pytest

from app.services.pipeline_runtime import (
    CollectorSink,
    ExecutionMode,
    NullSink,
    PipelineEvent,
    PipelineRuntime,
    RuntimeConfig,
    _ExecutionPathTaggingSink,
)
from ai_engine.agents.event_taxonomy import (
    EXECUTION_PATH_AGENT,
    EXECUTION_PATH_UNKNOWN,
)


def _make_runtime(sink=None):
    cfg = RuntimeConfig(mode=ExecutionMode.SYNC, user_id="u1")
    return PipelineRuntime(config=cfg, event_sink=sink)


def test_runtime_always_wraps_sink_in_execution_path_tagger() -> None:
    inner = CollectorSink()
    rt = _make_runtime(inner)
    assert isinstance(rt.sink, _ExecutionPathTaggingSink)
    # The wrapper holds the inner sink, not vice-versa.
    assert rt.sink._inner is inner


def test_runtime_with_no_sink_wraps_a_nullsink() -> None:
    rt = _make_runtime(None)
    assert isinstance(rt.sink, _ExecutionPathTaggingSink)
    assert isinstance(rt.sink._inner, NullSink)


@pytest.mark.asyncio
async def test_emit_stamps_execution_path_on_every_event() -> None:
    inner = CollectorSink()
    rt = _make_runtime(inner)
    rt._execution_path = EXECUTION_PATH_AGENT

    await rt.sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=10))
    await rt.sink.emit(PipelineEvent(event_type="agent_status", phase="atlas"))

    assert len(inner.events) == 2
    for ev in inner.events:
        assert ev.data["execution_path"] == EXECUTION_PATH_AGENT


@pytest.mark.asyncio
async def test_emit_does_not_overwrite_pre_existing_execution_path() -> None:
    """`setdefault` semantics: explicit per-event tags must win over the
    runtime-level default. This lets a sub-pipeline mark a specific event
    as e.g. EXECUTION_PATH_LEGACY for replay, without the wrapper
    clobbering it back."""
    inner = CollectorSink()
    rt = _make_runtime(inner)
    rt._execution_path = EXECUTION_PATH_AGENT

    ev = PipelineEvent(
        event_type="progress",
        data={"execution_path": "explicit-override"},
    )
    await rt.sink.emit(ev)

    assert inner.events[0].data["execution_path"] == "explicit-override"


@pytest.mark.asyncio
async def test_emit_handles_none_data_defensively() -> None:
    inner = CollectorSink()
    rt = _make_runtime(inner)
    rt._execution_path = EXECUTION_PATH_UNKNOWN

    ev = PipelineEvent(event_type="progress")
    ev.data = None  # type: ignore[assignment]
    await rt.sink.emit(ev)

    assert inner.events[0].data == {"execution_path": EXECUTION_PATH_UNKNOWN}


def test_wrapper_forwards_inner_attributes_transparently() -> None:
    """Callers that previously held a `CollectorSink` keep working when
    they hold the wrapped sink instead — `.events` and any other inner
    attribute is reachable via `__getattr__`."""
    inner = CollectorSink()
    rt = _make_runtime(inner)

    # `.events` lives on CollectorSink, not on the wrapper.
    assert rt.sink.events is inner.events


@pytest.mark.asyncio
async def test_close_propagates_to_inner_sink() -> None:
    closed = {"flag": False}

    class _Probe(NullSink):
        async def close(self) -> None:
            closed["flag"] = True

    rt = _make_runtime(_Probe())
    await rt.sink.close()
    assert closed["flag"] is True
