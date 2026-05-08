"""Pipeline checkpoint store for per-stage Temporal activity resume.

ADR-0036, m8-pr32. Each (job_id, stage) row records one execution of one
pipeline phase. The per-stage Temporal activity reads the checkpoint at
the start of each call and skips if status='complete'. Worker crash
mid-pipeline => next attempt sees the checkpoint and resumes from the
first non-complete stage.

Design notes
------------
- All writes are best-effort. Insert/update exceptions are LOGGED but never
  raised back into the activity body. A checkpoint-store outage must NOT
  block a generation job.
- output_summary is JSON-serialised by the caller and capped at
  ``CHECKPOINT_SUMMARY_MAX_BYTES`` before write. Larger payloads are
  truncated with a marker key ``__truncated__: true`` so Temporal activity
  history (which carries activity results) stays bounded.
- Reads return ``None`` for "no row" so the activity body can treat it the
  same as "row exists with status!=complete".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("hirestack.temporal.checkpoints")

CHECKPOINTS_TABLE = "pipeline_checkpoints"

# 4 KB output_summary cap. Keeps Temporal history bounded.
CHECKPOINT_SUMMARY_MAX_BYTES = 4 * 1024


@dataclass
class Checkpoint:
    """Snapshot of one (job_id, stage) row."""

    job_id: str
    stage: str
    status: str
    attempt_count: int
    output_summary: Optional[dict[str, Any]] = None
    error_class: Optional[str] = None
    completed_at: Optional[datetime] = None


def _truncate_summary(summary: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return ``summary`` if its JSON encoding fits under the cap; otherwise
    a sentinel ``{"__truncated__": True, "original_bytes": N}``.

    We deliberately do NOT try to partially preserve fields — a partial
    summary is more dangerous (silent data loss) than a clear marker.
    """
    if summary is None:
        return None
    try:
        encoded = json.dumps(summary, default=str)
    except Exception as exc:  # noqa: BLE001 — any encode failure must not raise
        logger.warning(
            "checkpoint_summary_encode_failed",
            extra={"error": str(exc), "error_class": exc.__class__.__name__},
        )
        return {"__truncated__": True, "reason": "encode_failed"}
    if len(encoded.encode("utf-8")) <= CHECKPOINT_SUMMARY_MAX_BYTES:
        return summary
    return {"__truncated__": True, "original_bytes": len(encoded.encode("utf-8"))}


class CheckpointStore:
    """Thin Postgres wrapper for ``pipeline_checkpoints``.

    Constructed with a Supabase client (service role). All writes are
    best-effort — exceptions are logged but never raised back to the caller
    so a checkpoint-store outage does not block generation.
    """

    def __init__(self, supabase: Any, *, table: str = CHECKPOINTS_TABLE) -> None:
        self._supabase = supabase
        self._table = table

    # ── Reads ─────────────────────────────────────────────────────────
    def read(self, job_id: str, stage: str) -> Optional[Checkpoint]:
        """Return the checkpoint for (job_id, stage) or ``None`` if missing
        or on read failure (read failure logs and returns None — the
        activity body must treat None as "must execute")."""
        try:
            resp = (
                self._supabase.table(self._table)
                .select("*")
                .eq("job_id", job_id)
                .eq("stage", stage)
                .maybe_single()
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning(
                "checkpoint_read_failed",
                extra={
                    "job_id": job_id,
                    "stage": stage,
                    "error_class": exc.__class__.__name__,
                    "error": str(exc)[:200],
                },
            )
            return None
        row = getattr(resp, "data", None)
        if not row:
            return None
        return Checkpoint(
            job_id=row.get("job_id"),
            stage=row.get("stage"),
            status=row.get("status", ""),
            attempt_count=int(row.get("attempt_count", 1)),
            output_summary=row.get("output_summary"),
            error_class=row.get("error_class"),
            completed_at=row.get("completed_at"),
        )

    def is_complete(self, job_id: str, stage: str) -> bool:
        """Convenience: True iff the checkpoint exists with status='complete'."""
        cp = self.read(job_id, stage)
        return cp is not None and cp.status == "complete"

    # ── Writes (all best-effort, never raise) ─────────────────────────
    def mark_running(self, job_id: str, stage: str) -> None:
        """Upsert (job_id, stage) with status='running', incrementing
        attempt_count if the row already exists. Best-effort.
        """
        existing = self.read(job_id, stage)
        attempt = (existing.attempt_count + 1) if existing else 1
        payload = {
            "job_id": job_id,
            "stage": stage,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "attempt_count": attempt,
            "completed_at": None,
            "error_class": None,
        }
        self._upsert(payload, action="mark_running")

    def mark_complete(
        self,
        job_id: str,
        stage: str,
        summary: Optional[dict[str, Any]] = None,
    ) -> None:
        """Upsert with status='complete', completed_at=now(),
        output_summary=truncated(summary). Best-effort."""
        payload = {
            "job_id": job_id,
            "stage": stage,
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "output_summary": _truncate_summary(summary),
            "error_class": None,
        }
        self._upsert(payload, action="mark_complete")

    def mark_failed(self, job_id: str, stage: str, error_class: str) -> None:
        """Upsert with status='failed', error_class=<qualified class name>.
        Best-effort. Does NOT clear completed_at — a previously-complete
        stage that mysteriously fails should keep its completion timestamp
        for forensics; the status flip is the source of truth."""
        payload = {
            "job_id": job_id,
            "stage": stage,
            "status": "failed",
            "error_class": (error_class or "")[:200],
        }
        self._upsert(payload, action="mark_failed")

    # ── Internal ──────────────────────────────────────────────────────
    def _upsert(self, payload: dict[str, Any], *, action: str) -> None:
        try:
            (
                self._supabase.table(self._table)
                .upsert(payload, on_conflict="job_id,stage")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning(
                "checkpoint_write_failed",
                extra={
                    "action": action,
                    "job_id": payload.get("job_id"),
                    "stage": payload.get("stage"),
                    "error_class": exc.__class__.__name__,
                    "error": str(exc)[:200],
                },
            )


__all__ = [
    "CHECKPOINTS_TABLE",
    "CHECKPOINT_SUMMARY_MAX_BYTES",
    "Checkpoint",
    "CheckpointStore",
]
