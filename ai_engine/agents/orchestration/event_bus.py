"""
Typed event bus for the v4 agent orchestrator.

Every meaningful thing that happens during a pipeline emits a typed event.
Events are the substrate for:

  - The Mission Control UI (subscribes to live events)
  - The persistence layer (writes to generation_job_events)
  - The Critic agent (reasons over event streams)
  - Replay / debugging (a run can be reconstructed from its event log)

This module defines:

  - OrchestrationEvent: the canonical typed event payload
  - EventLevel: severity of an event
  - EventBus: the protocol the orchestrator depends on
  - InMemoryEventBus: a default in-process implementation that fans events
    out to N async subscribers; used by tests and the future durable
    forwarder that bridges into pipeline_runtime's existing EventSink.

Pure foundation — no DB, no network on import.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol


class EventLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class OrchestrationEvent:
    """Canonical event shape carried on the bus."""

    # What kind of event this is. Free-form string so callers can be precise
    # without bloating an enum (e.g. "agent.atlas.benchmark.completed").
    event_name: str

    # Which application this event belongs to (None = global).
    application_id: Optional[str] = None

    # Which agent (if any) emitted the event.
    agent_name: Optional[str] = None

    # Module key for per-document events (e.g. "cv", "benchmark.cv").
    module_key: Optional[str] = None

    # Severity.
    level: EventLevel = EventLevel.INFO

    # Human-readable message for UI surfaces.
    message: str = ""

    # Arbitrary structured payload. Keep small — anything large should be
    # persisted as an artifact and referenced by id here.
    data: Dict[str, Any] = field(default_factory=dict)

    # Wall-clock emission time.
    emitted_at: str = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────
#  Bus protocol + default implementation
# ─────────────────────────────────────────────────────────────────────────


Subscriber = Callable[[OrchestrationEvent], Awaitable[None]]


class EventBus(Protocol):
    """Anything the orchestrator can publish events to."""

    async def publish(self, event: OrchestrationEvent) -> None: ...

    def subscribe(self, subscriber: Subscriber) -> None: ...


class InMemoryEventBus:
    """In-process event bus — fans out to subscribers concurrently.

    Subscriber failures are isolated: if one subscriber raises, others still
    receive the event. This matches the production ethos that no single
    sink can stop the pipeline.
    """

    def __init__(self) -> None:
        self._subs: List[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subs.append(subscriber)

    async def publish(self, event: OrchestrationEvent) -> None:
        if not self._subs:
            return
        # Fan out concurrently; gather with return_exceptions so one bad
        # subscriber cannot poison the rest.
        await asyncio.gather(
            *(self._safe_call(s, event) for s in self._subs),
            return_exceptions=True,
        )

    @staticmethod
    async def _safe_call(sub: Subscriber, event: OrchestrationEvent) -> None:
        try:
            await sub(event)
        except Exception:
            # Swallow — subscribers must not break the bus.
            pass
