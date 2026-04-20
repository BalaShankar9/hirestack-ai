"""
EventBusBridge — forwards typed OrchestrationEvents to the legacy
PipelineEvent EventSink chain (DatabaseSink, SSESink, CollectorSink).

This is the adapter that lets the v4 orchestrator (Planner / Critic /
ArtifactStore / typed agents) coexist with the existing pipeline_runtime
infrastructure without rewriting the persistence + SSE layer.

How it works:
  1. The pipeline runtime owns a single EventSink (one of NullSink,
     CollectorSink, SSESink, DatabaseSink) — same as today.
  2. We instantiate an InMemoryEventBus and an EventBusBridge that
     subscribes to it and forwards every OrchestrationEvent into the
     runtime's existing sink as a PipelineEvent.
  3. Existing consumers (Mission Control polling, SSE clients, the
     generation_jobs row updater) keep working unchanged. New typed
     events (plan_created, artifact_created, validation_passed, …)
     just flow through.

Mapping rules:
  - event_name → event_type (preserved as-is, free-form)
  - data["phase"] → phase (or inferred from agent_name)
  - data["progress"] → progress
  - level → status ("error" → "failed", "warning" → "warning",
    "info"/"debug" → "running")
  - message → message
  - all other data fields pass through verbatim
"""
from __future__ import annotations

from typing import Optional

import structlog

from ai_engine.agents.orchestration.event_bus import (
    EventLevel,
    InMemoryEventBus,
    OrchestrationEvent,
)

logger = structlog.get_logger(__name__)


# Local import-time alias kept lazy to avoid a circular import — the
# pipeline_runtime module imports from a lot of places and this module
# is consumed by it.
def _phase_from_agent(agent: Optional[str]) -> str:
    if not agent:
        return ""
    a = agent.lower()
    # Known canonical 7-phase agents.
    for phase in ("recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova"):
        if phase in a:
            return phase
    return ""


def _status_from_level(level: EventLevel) -> str:
    if level == EventLevel.ERROR:
        return "failed"
    if level == EventLevel.WARNING:
        return "warning"
    return "running"


class EventBusBridge:
    """Subscribes to an InMemoryEventBus and re-emits onto an EventSink."""

    def __init__(self, bus: InMemoryEventBus, sink: "EventSink") -> None:  # noqa: F821
        self._bus = bus
        self._sink = sink
        bus.subscribe(self._on_event)

    async def _on_event(self, event: OrchestrationEvent) -> None:
        # Lazy import to keep this module zero-cost on import.
        try:
            from app.services.pipeline_runtime import PipelineEvent
        except Exception as ex:  # pragma: no cover
            logger.warning("event_bus_bridge.import_failed", error=str(ex)[:200])
            return

        data = dict(event.data or {})
        phase = str(data.pop("phase", "") or _phase_from_agent(event.agent_name))
        progress_raw = data.pop("progress", None)
        try:
            progress = int(progress_raw) if progress_raw is not None else 0
        except (TypeError, ValueError):
            progress = 0
        stage = str(data.pop("stage", "") or "")
        latency_ms_raw = data.pop("latency_ms", 0)
        try:
            latency_ms = int(latency_ms_raw)
        except (TypeError, ValueError):
            latency_ms = 0

        # Carry the typed metadata in the data payload so DB/SSE consumers
        # see them without changing their schema.
        if event.application_id:
            data.setdefault("application_id", event.application_id)
        if event.agent_name:
            data.setdefault("agent_name", event.agent_name)
        if event.module_key:
            data.setdefault("module_key", event.module_key)
        data.setdefault("level", event.level.value if isinstance(event.level, EventLevel) else str(event.level))

        pevent = PipelineEvent(
            event_type=event.event_name,
            phase=phase,
            progress=progress,
            message=event.message or "",
            data=data,
            pipeline_name=event.agent_name or "",
            stage=stage,
            status=_status_from_level(event.level),
            latency_ms=latency_ms,
        )

        try:
            await self._sink.emit(pevent)
        except Exception as ex:
            # Sink failures must never poison the bus — log and move on.
            logger.warning("event_bus_bridge.sink_emit_failed",
                           event_name=event.event_name, error=str(ex)[:200])
