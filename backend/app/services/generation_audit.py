"""Generation audit trail — P2-14.

Records a structured audit event every time a generation job starts,
completes, or fails.  Writes to two sinks:

1. ``structlog`` — always, zero-latency, shows in log aggregators.
2. ``generation_audit_log`` Supabase table — best-effort, queryable.

The table schema (applied via migration 20260502000000) is::

    CREATE TABLE generation_audit_log (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     TEXT NOT NULL,
        job_id      TEXT NOT NULL,
        application_id TEXT NOT NULL,
        event       TEXT NOT NULL,          -- 'started' | 'completed' | 'failed' | 'cancelled'
        modules     JSONB,                  -- requested module list
        jd_len      INT,                    -- length of jd_text (not the text itself)
        resume_provided BOOLEAN,
        duration_ms INT,                    -- ms from started → this event
        model_used  TEXT,                   -- primary model name
        output_quality JSONB,               -- {cv: score, cover_letter: score, …}
        error_message TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
    );

Consumers can query the table for:
- Generation success rate per user / per day
- Average generation duration
- Quality score trends
- Modules most commonly requested
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("hirestack.audit")

# Table name — keep in sync with the migration
_AUDIT_TABLE = "generation_audit_log"
# Maximum length for error_message stored in the audit log
_ERROR_MSG_MAX_LEN = 500


class GenerationAuditLogger:
    """Thin façade that emits structured audit events for generation jobs.

    Usage::

        audit = GenerationAuditLogger(user_id, job_id, application_id)
        audit.log_started(modules=["cv", "coverLetter"], jd_len=3200, resume_provided=True)
        # ... pipeline runs ...
        audit.log_completed(duration_ms=45_000, model_used="gemini-2.5-pro",
                            output_quality={"cv": 88, "cover_letter": 82})
    """

    def __init__(self, user_id: str, job_id: str, application_id: str) -> None:
        self._user_id = user_id
        self._job_id = job_id
        self._application_id = application_id
        self._started_at: Optional[float] = None  # monotonic

    # ── Public API ─────────────────────────────────────────────────────

    def log_started(
        self,
        *,
        modules: List[str],
        jd_len: int = 0,
        resume_provided: bool = True,
    ) -> None:
        """Emit 'started' audit event.  Call this when the runner begins."""
        self._started_at = time.monotonic()
        logger.info(
            "generation_audit",
            user_id=self._user_id,
            job_id=self._job_id,
            application_id=self._application_id,
            audit_event="started",
            modules=modules,
            jd_len=jd_len,
            resume_provided=resume_provided,
        )
        self._persist_async({
            "event": "started",
            "modules": modules,
            "jd_len": jd_len,
            "resume_provided": resume_provided,
        })

    def log_completed(
        self,
        *,
        duration_ms: Optional[int] = None,
        model_used: Optional[str] = None,
        output_quality: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit 'completed' audit event."""
        if duration_ms is None and self._started_at is not None:
            duration_ms = int((time.monotonic() - self._started_at) * 1000)
        logger.info(
            "generation_audit",
            user_id=self._user_id,
            job_id=self._job_id,
            application_id=self._application_id,
            audit_event="completed",
            duration_ms=duration_ms,
            model_used=model_used,
            output_quality=output_quality or {},
        )
        self._persist_async({
            "event": "completed",
            "duration_ms": duration_ms,
            "model_used": model_used,
            "output_quality": output_quality or {},
        })

    def log_failed(
        self,
        *,
        error_message: str,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Emit 'failed' audit event."""
        if duration_ms is None and self._started_at is not None:
            duration_ms = int((time.monotonic() - self._started_at) * 1000)
        truncated_msg = error_message[:_ERROR_MSG_MAX_LEN]
        logger.warning(
            "generation_audit",
            user_id=self._user_id,
            job_id=self._job_id,
            application_id=self._application_id,
            audit_event="failed",
            duration_ms=duration_ms,
            error_message=truncated_msg,
        )
        self._persist_async({
            "event": "failed",
            "duration_ms": duration_ms,
            "error_message": truncated_msg,
        })

    def log_cancelled(self, *, duration_ms: Optional[int] = None) -> None:
        """Emit 'cancelled' audit event."""
        if duration_ms is None and self._started_at is not None:
            duration_ms = int((time.monotonic() - self._started_at) * 1000)
        logger.info(
            "generation_audit",
            user_id=self._user_id,
            job_id=self._job_id,
            application_id=self._application_id,
            audit_event="cancelled",
            duration_ms=duration_ms,
        )
        self._persist_async({
            "event": "cancelled",
            "duration_ms": duration_ms,
        })

    # ── Internal ───────────────────────────────────────────────────────

    def _persist_async(self, row_data: Dict[str, Any]) -> None:
        """Best-effort persist to DB.  Never raises — failures only log a warning."""
        import asyncio

        row = {
            "user_id": self._user_id,
            "job_id": self._job_id,
            "application_id": self._application_id,
            "event": row_data.get("event"),
            "modules": row_data.get("modules"),
            "jd_len": row_data.get("jd_len"),
            "resume_provided": row_data.get("resume_provided"),
            "duration_ms": row_data.get("duration_ms"),
            "model_used": row_data.get("model_used"),
            "output_quality": row_data.get("output_quality"),
            "error_message": row_data.get("error_message"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._write_row(row))
        except RuntimeError:
            # No running loop (e.g., test context) — skip DB write
            pass

    @staticmethod
    async def _write_row(row: Dict[str, Any]) -> None:
        """Fire-and-forget write to the audit table."""
        try:
            from app.core.database import get_supabase
            sb = get_supabase()
            import asyncio
            await asyncio.to_thread(
                lambda: sb.table(_AUDIT_TABLE).insert(row).execute()
            )
        except Exception as exc:
            logger.warning("generation_audit.db_write_failed", error=str(exc)[:200])


def make_audit_logger(
    user_id: str, job_id: str, application_id: str
) -> GenerationAuditLogger:
    """Factory for a GenerationAuditLogger instance."""
    return GenerationAuditLogger(user_id, job_id, application_id)
