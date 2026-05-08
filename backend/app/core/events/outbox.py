"""Outbox writer (PR-8).

Thin layer over the Supabase client that appends `EventEnvelope`s to the
`events_outbox` table. The DB UNIQUE constraint on (org_id, idempotency_key)
does the dedupe; this writer just translates the violation into a lookup of
the pre-existing row.

PR-9 will introduce the relay that drains the table.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .envelope import EventEnvelope
from .schema_registry import (
    EventValidationError,
    MissingEventSchema,
    validate_event,
)

logger = logging.getLogger(__name__)

_UNIQUE_VIOLATION = "23505"  # Postgres SQLSTATE
OUTBOX_TABLE = "events_outbox"


class _SupabaseTableLike(Protocol):
    def insert(self, row: dict[str, Any], *args: Any, **kwargs: Any) -> Any: ...
    def select(self, *args: Any, **kwargs: Any) -> Any: ...


class _SupabaseClientLike(Protocol):
    def table(self, name: str) -> _SupabaseTableLike: ...


def _strict_flag_enabled() -> bool:
    """Read ``ff_strict_event_validation`` lazily (per ADR-0035)."""
    try:
        from app.core.config import get_settings  # type: ignore
    except Exception:  # noqa: BLE001 — config import optional at module load
        return False
    try:
        return bool(getattr(get_settings(), "ff_strict_event_validation", False))
    except Exception:  # noqa: BLE001 — defensive: never fail OutboxWriter on config read
        return False


class OutboxWriter:
    """Append envelopes to ``events_outbox`` idempotently."""

    def __init__(
        self,
        supabase: _SupabaseClientLike,
        *,
        table: str = OUTBOX_TABLE,
        strict: bool | None = None,
    ) -> None:
        self._supabase = supabase
        self._table = table
        # ``None`` ⇒ read the live flag at append time.
        # ``True``/``False`` ⇒ explicit override (used by tests).
        self._strict_override = strict

    def _is_strict(self) -> bool:
        if self._strict_override is not None:
            return self._strict_override
        return _strict_flag_enabled()

    def _validate_or_raise(self, envelope: EventEnvelope) -> None:
        """Validate envelope against its JSON Schema (ADR-0035).

        Behaviour:
          * Validation passes → return.
          * Validation fails AND ``strict=False`` → log
            ``event_validation_failed_shadow`` and return (insert proceeds).
          * Validation fails AND ``strict=True`` → raise
            :class:`EventValidationError`.
          * Schema missing AND ``strict=False`` → log
            ``event_schema_missing_shadow`` and return.
          * Schema missing AND ``strict=True`` → raise
            :class:`MissingEventSchema`.
        """
        strict = self._is_strict()
        try:
            errors = validate_event(envelope)
        except MissingEventSchema as exc:
            if strict:
                raise
            logger.warning(
                "event_schema_missing_shadow",
                extra={
                    "event_type": exc.event_type,
                    "event_version": exc.event_version,
                },
            )
            return
        except Exception as exc:  # noqa: BLE001 — never let validator quirks block writes
            logger.warning(
                "event_validator_internal_error",
                extra={
                    "event_type": envelope.event_type,
                    "event_version": envelope.event_version,
                    "error": repr(exc),
                },
            )
            return

        if not errors:
            return

        if strict:
            raise EventValidationError(
                envelope.event_type, envelope.event_version, errors
            )

        logger.warning(
            "event_validation_failed_shadow",
            extra={
                "event_type": envelope.event_type,
                "event_version": envelope.event_version,
                "error_count": len(errors),
                "errors": errors[:5],  # cap log size
            },
        )

    def append(self, envelope: EventEnvelope) -> dict[str, Any]:
        """Insert ``envelope``; return inserted-or-existing row."""
        self._validate_or_raise(envelope)
        row = envelope.to_outbox_row()
        try:
            response = self._supabase.table(self._table).insert(row).execute()
        except Exception as exc:  # noqa: BLE001 — supabase wraps loosely
            if envelope.idempotency_key is not None and _is_unique_violation(exc):
                existing = self._fetch_existing(
                    org_id=row["org_id"],
                    idempotency_key=envelope.idempotency_key,
                )
                if existing is not None:
                    logger.info(
                        "events_outbox dedupe hit",
                        extra={
                            "event_type": envelope.event_type,
                            "org_id": row["org_id"],
                            "idempotency_key": envelope.idempotency_key,
                        },
                    )
                    return existing
            raise

        data = getattr(response, "data", None)
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return row

    def _fetch_existing(self, *, org_id: str, idempotency_key: str) -> dict[str, Any] | None:
        try:
            response = (
                self._supabase.table(self._table)
                .select("*")
                .eq("org_id", org_id)
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
            )
        except Exception:  # noqa: BLE001
            logger.exception("events_outbox dedupe lookup failed")
            return None
        data = getattr(response, "data", None)
        if isinstance(data, list) and data:
            return data[0]
        return None


def _is_unique_violation(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code == _UNIQUE_VIOLATION:
        return True
    msg = str(exc).lower()
    return "duplicate key" in msg or "unique constraint" in msg or _UNIQUE_VIOLATION in msg
