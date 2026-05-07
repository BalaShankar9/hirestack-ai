"""Domain event surface (PR-8 outbox foundation)."""

from .envelope import EventEnvelope
from .outbox import OUTBOX_TABLE, OutboxWriter
from .types import (
    AIM_ASSIGNMENT_CREATED,
    AIM_SOURCE_CREATED,
    GENERATION_COMPLETED,
    GENERATION_REQUESTED,
    MISSION_DRAFT_CREATED,
    REGISTERED_EVENT_TYPES,
    EventType,
    current_version,
    is_registered,
)

__all__ = [
    "EventEnvelope",
    "OutboxWriter",
    "OUTBOX_TABLE",
    "EventType",
    "REGISTERED_EVENT_TYPES",
    "current_version",
    "is_registered",
    "AIM_ASSIGNMENT_CREATED",
    "AIM_SOURCE_CREATED",
    "GENERATION_REQUESTED",
    "GENERATION_COMPLETED",
    "MISSION_DRAFT_CREATED",
]
