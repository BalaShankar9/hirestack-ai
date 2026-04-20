"""
v4 orchestration foundation package.

Currently exposes a typed in-process event bus that the pipeline runtime
forwards through ``app.services.event_bus_bridge.EventBusBridge`` onto
the SSE event sink. This package will grow as further agentic primitives
become genuinely load-bearing in production. Anything that is not
imported by ``app.services.pipeline_runtime`` (directly or transitively)
must not live here — half-built agent infrastructure that the UI
implies is active is worse than no architecture at all.
"""
from __future__ import annotations

from .event_bus import (
    EventBus,
    EventLevel,
    InMemoryEventBus,
    OrchestrationEvent,
)

__all__ = [
    "EventBus",
    "EventLevel",
    "InMemoryEventBus",
    "OrchestrationEvent",
]
