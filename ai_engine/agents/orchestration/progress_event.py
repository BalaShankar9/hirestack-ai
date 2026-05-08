from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

ORCHESTRATION_PROGRESS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class WorkflowProgressEvent:
    """Canonical progress payload shared by active orchestrators."""

    pipeline_name: str
    stage: str
    status: Any
    message: str = ""
    latency_ms: int = 0
    progress: Optional[int] = None
    workflow_id: Optional[str] = None
    phase: Optional[str] = None
    event_type: str = "agent_status"
    slide_idx: Optional[int] = None
    schema_version: str = ORCHESTRATION_PROGRESS_SCHEMA_VERSION

    @property
    def status_value(self) -> str:
        if isinstance(self.status, Enum):
            return str(self.status.value)
        return str(self.status)

    @property
    def phase_name(self) -> str:
        if self.phase:
            return self.phase
        return self.stage

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "pipeline_name": self.pipeline_name,
            "stage": self.stage,
            "phase": self.phase_name,
            "status": self.status_value,
            "latency_ms": self.latency_ms,
            "message": self.message,
        }
        if self.progress is not None:
            payload["progress"] = self.progress
        if self.workflow_id:
            payload["workflow_id"] = self.workflow_id
        if self.slide_idx is not None:
            payload["slide_idx"] = self.slide_idx
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        default_event_type: str = "agent_status",
    ) -> "WorkflowProgressEvent":
        stage = str(payload.get("stage") or payload.get("phase") or "")
        return cls(
            pipeline_name=str(payload.get("pipeline_name") or ""),
            stage=stage,
            status=payload.get("status", ""),
            message=str(payload.get("message") or ""),
            latency_ms=int(payload.get("latency_ms") or 0),
            progress=payload.get("progress"),
            workflow_id=payload.get("workflow_id"),
            phase=str(payload.get("phase") or stage),
            event_type=str(payload.get("event_type") or default_event_type),
            slide_idx=payload.get("slide_idx"),
            schema_version=str(
                payload.get("schema_version") or ORCHESTRATION_PROGRESS_SCHEMA_VERSION
            ),
        )


def coerce_progress_event(
    payload: Any,
    *,
    default_event_type: str = "agent_status",
) -> WorkflowProgressEvent:
    if isinstance(payload, WorkflowProgressEvent):
        return payload
    if hasattr(payload, "to_payload") and callable(payload.to_payload):
        payload = payload.to_payload()
    if isinstance(payload, Mapping):
        return WorkflowProgressEvent.from_payload(
            payload,
            default_event_type=default_event_type,
        )
    raise TypeError(f"Unsupported progress payload type: {type(payload)!r}")