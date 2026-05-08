"""Event envelope schema (PR-8).

Wire shape for every domain event: identity, type, tenant scoping, and a
typed JSON payload. Same shape lands in `events_outbox` and (PR-9) flows
out via Redis Streams.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .types import REGISTERED_EVENT_TYPES, current_version


class EventEnvelope(BaseModel):
    """Canonical wrapper around a domain event payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    event_version: int = Field(..., ge=1)
    org_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str | None = Field(default=None, max_length=255)
    payload: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return v.astimezone(timezone.utc)

    @field_validator("event_type")
    @classmethod
    def _require_registered(cls, v: str) -> str:
        if v not in REGISTERED_EVENT_TYPES:
            raise ValueError(
                f"unknown event_type {v!r}; register it in app.core.events.types first"
            )
        return v

    def model_post_init(self, __context: Any) -> None:
        expected = current_version(self.event_type)
        if self.event_version != expected:
            raise ValueError(
                f"event_version {self.event_version} != registered version "
                f"{expected} for {self.event_type!r}"
            )

    def to_outbox_row(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "org_id": str(self.org_id),
            "occurred_at": self.occurred_at.isoformat(),
            "idempotency_key": self.idempotency_key,
            "payload": dict(self.payload),
        }
