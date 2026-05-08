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
from .phase_contract import (
    INTERVIEW_SESSION_PHASE_ORDER,
    PPT_GENERATION_PHASE_ORDER,
    PPT_RENDER_PHASE_ORDER,
    VIDEO_PITCH_PHASE_ORDER,
    WorkflowPhaseStatus,
    get_workflow_phase_order,
    is_terminal_workflow_phase,
)
from .progress_event import (
    ORCHESTRATION_PROGRESS_SCHEMA_VERSION,
    WorkflowProgressEvent,
    coerce_progress_event,
)
from .timed_workflow import TimedWorkflow

__all__ = [
    "EventBus",
    "EventLevel",
    "InMemoryEventBus",
    "OrchestrationEvent",
    "WorkflowPhaseStatus",
    "PPT_GENERATION_PHASE_ORDER",
    "PPT_RENDER_PHASE_ORDER",
    "VIDEO_PITCH_PHASE_ORDER",
    "INTERVIEW_SESSION_PHASE_ORDER",
    "get_workflow_phase_order",
    "is_terminal_workflow_phase",
    "ORCHESTRATION_PROGRESS_SCHEMA_VERSION",
    "WorkflowProgressEvent",
    "coerce_progress_event",
    "TimedWorkflow",
]
