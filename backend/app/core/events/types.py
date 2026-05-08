"""Domain event types and registry.

Stable string identifiers for events captured in `events_outbox`. Bumping
`event_version` for an existing type is a contract change and requires a
new consumer migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class EventType:
    """Identifier + current schema version for an event type."""

    name: str
    version: int

    @property
    def qualified(self) -> str:
        """Wire form: ``aim.assignment.created v1``."""
        return f"{self.name} v{self.version}"


# ---------------------------------------------------------------------------
# Registered types (PR-8 initial set, per BUILD_PLAN_M1_M6 §M3.PR-8).
# ---------------------------------------------------------------------------

AIM_ASSIGNMENT_CREATED = EventType("aim.assignment.created", 1)
AIM_SOURCE_CREATED = EventType("aim.source.created", 1)
GENERATION_REQUESTED = EventType("generation.requested", 1)
GENERATION_COMPLETED = EventType("generation.completed", 1)
MISSION_DRAFT_CREATED = EventType("mission.draft.created", 1)


REGISTERED_EVENT_TYPES: Mapping[str, EventType] = {
    et.name: et
    for et in (
        AIM_ASSIGNMENT_CREATED,
        AIM_SOURCE_CREATED,
        GENERATION_REQUESTED,
        GENERATION_COMPLETED,
        MISSION_DRAFT_CREATED,
    )
}


def is_registered(event_type_name: str) -> bool:
    """Return True iff ``event_type_name`` is a known event type."""
    return event_type_name in REGISTERED_EVENT_TYPES


def current_version(event_type_name: str) -> int:
    """Look up the current registered version for ``event_type_name``.

    Raises:
        KeyError: if the event type is not registered.
    """
    return REGISTERED_EVENT_TYPES[event_type_name].version
