"""AIM \u2014 streaming-event persistence sink.

Mirrors the canonical :class:`~app.services.pipeline_runtime.DatabaseSink`
but writes to ``aim_section_events`` instead of ``generation_job_events``.

Used by the SSE route alongside :class:`SSESink` so:
  * the live agent dock can subscribe via Supabase realtime,
  * `?since=` resume / dedup-on-event_id work on the client,
  * post-mortem replay of a section generation is possible.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import structlog

from app.core.database import SupabaseDB, TABLES, get_db
from app.services.pipeline_runtime import EventSink, PipelineEvent

logger = structlog.get_logger("hirestack.aim.event_sink")


class AIMDatabaseSink(EventSink):
    """Persist AIM streaming events to ``aim_section_events``.

    A failed write must NEVER bubble up: the SSE stream is the source of
    truth for the live UI, persistence is best-effort durable history.
    """

    def __init__(
        self,
        section_id: str,
        user_id: str,
        *,
        db: Optional[SupabaseDB] = None,
    ) -> None:
        self._section_id = section_id
        self._user_id = user_id
        self._db = db or get_db()
        self._sequence = 0

    async def emit(self, event: PipelineEvent) -> None:
        # data is JSONB; ensure JSON-serialisable (drop non-serialisable values)
        try:
            data = json.loads(json.dumps(event.data or {}, default=str))
        except Exception:  # noqa: BLE001
            data = {}
        raw_sequence = data.get("sequence")
        if isinstance(raw_sequence, int):
            sequence = raw_sequence
            self._sequence = max(self._sequence, sequence)
        else:
            self._sequence += 1
            sequence = self._sequence
        event_id = str(data.get("event_id") or uuid.uuid4())
        row = {
            "event_id": event_id,
            "section_id": self._section_id,
            "user_id": self._user_id,
            "sequence": sequence,
            "event_type": event.event_type,
            "agent": event.stage or event.phase or "",
            "status": event.status or "",
            "message": (event.message or "")[:5000],
            "progress": int(event.progress or 0),
            "latency_ms": int(event.latency_ms or 0),
            "data": data,
        }
        try:
            await self._db.create(TABLES["aim_section_events"], row)
        except Exception as exc:  # noqa: BLE001
            # Best-effort persistence: never poison the live SSE flow.
            logger.warning(
                "aim_section_event_persist_failed",
                section_id=self._section_id,
                event_type=event.event_type,
                sequence=sequence,
                error=str(exc),
            )

    async def emit_token_delta(self, **_kwargs: Any) -> None:
        # Token-level deltas are NEVER persisted (would explode the table).
        return None
