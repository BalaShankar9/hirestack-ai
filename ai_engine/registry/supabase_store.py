"""Supabase-backed ``ToolStore`` and audit sink (PR m6-pr25).

Production wiring for the registry that PR m5-pr14 built:

* ``SupabaseToolStore`` reads ``ai_tools`` and ``ai_agent_tool_grants``
  on demand, with a tiny TTL cache so a single agent run doesn't
  hammer Supabase. Cache is process-local; rows refresh after
  ``ttl_seconds`` (default 60s) so grants edited from the dashboard
  propagate within a minute.
* ``supabase_invocation_sink`` writes a row into ``ai_tool_invocations``
  for every dispatch. Wrapped in try/except — audit failure must never
  raise into the hot path (the dispatcher already has its own swallow,
  but defence in depth).

Both helpers are async and use ``asyncio.to_thread`` to keep the
synchronous Supabase client off the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .dispatcher import ToolInvocation
from .tools import ToolRecord, ToolStore

logger = logging.getLogger(__name__)


@dataclass
class _CachedTool:
    record: Optional[ToolRecord]
    expires_at: float


@dataclass
class _CachedGrant:
    granted: bool
    expires_at: float


@dataclass
class SupabaseToolStore(ToolStore):
    """Reads ``ai_tools`` + ``ai_agent_tool_grants`` with a TTL cache.

    Compatible with the ``ToolStore`` protocol consumed by ``Dispatcher``.
    Holds no connection state; resolves the Supabase client lazily on
    each call so the registry survives client re-init.
    """

    ttl_seconds: float = 60.0
    _tool_cache: dict[str, _CachedTool] = field(default_factory=dict)
    _grant_cache: dict[tuple[str, str], _CachedGrant] = field(default_factory=dict)

    async def get(self, tool_name: str) -> Optional[ToolRecord]:
        now = time.monotonic()
        cached = self._tool_cache.get(tool_name)
        if cached is not None and cached.expires_at > now:
            return cached.record
        record = await asyncio.to_thread(self._fetch_tool_sync, tool_name)
        self._tool_cache[tool_name] = _CachedTool(
            record=record, expires_at=now + self.ttl_seconds
        )
        return record

    async def has_grant(self, agent_name: str, tool_name: str) -> bool:
        now = time.monotonic()
        key = (agent_name, tool_name)
        cached = self._grant_cache.get(key)
        if cached is not None and cached.expires_at > now:
            return cached.granted
        granted = await asyncio.to_thread(
            self._fetch_grant_sync, agent_name, tool_name
        )
        self._grant_cache[key] = _CachedGrant(
            granted=granted, expires_at=now + self.ttl_seconds
        )
        return granted

    # ── sync DB calls (run on a worker thread) ────────────────────────
    def _fetch_tool_sync(self, tool_name: str) -> Optional[ToolRecord]:
        from app.core.database import get_supabase

        try:
            sb = get_supabase()
            resp = (
                sb.table("ai_tools")
                .select(
                    "name,version,description,code_ref,input_schema,output_schema,timeout_ms,enabled,"
                    "sandbox_tier,egress_allowlist,requires_capability_token"
                )
                .eq("name", tool_name)
                .eq("enabled", True)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool_registry.fetch_tool_failed", extra={"tool": tool_name, "error": str(exc)})
            return None

        rows = getattr(resp, "data", None) or []
        if not rows:
            return None
        row = rows[0]
        # PR m7-pr29: sandbox_tier / egress_allowlist / requires_capability_token
        # default to L0 / [] / False so older rows shipped before the
        # 20260508010000 migration still load cleanly under tests.
        return ToolRecord(
            name=row["name"],
            code_ref=row["code_ref"],
            description=row.get("description") or "",
            version=int(row.get("version") or 1),
            input_schema=row.get("input_schema") or {},
            output_schema=row.get("output_schema") or {},
            timeout_ms=int(row.get("timeout_ms") or 15_000),
            enabled=bool(row.get("enabled", True)),
            sandbox_tier=str(row.get("sandbox_tier") or "L0"),
            egress_allowlist=list(row.get("egress_allowlist") or []),
            requires_capability_token=bool(row.get("requires_capability_token") or False),
        )

    def _fetch_grant_sync(self, agent_name: str, tool_name: str) -> bool:
        from app.core.database import get_supabase

        try:
            sb = get_supabase()
            resp = (
                sb.table("ai_agent_tool_grants")
                .select("agent_name")
                .in_("agent_name", [agent_name, "*"])
                .eq("tool_name", tool_name)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tool_registry.fetch_grant_failed",
                extra={"agent": agent_name, "tool": tool_name, "error": str(exc)},
            )
            return False
        rows = getattr(resp, "data", None) or []
        return bool(rows)

    def invalidate(self, tool_name: Optional[str] = None) -> None:
        """Drop cache entries; useful for tests or admin reload."""
        if tool_name is None:
            self._tool_cache.clear()
            self._grant_cache.clear()
            return
        self._tool_cache.pop(tool_name, None)
        self._grant_cache = {
            k: v for k, v in self._grant_cache.items() if k[1] != tool_name
        }


# ── audit sink ────────────────────────────────────────────────────────
async def supabase_invocation_sink(invocation: ToolInvocation) -> None:
    """Write a row into ``ai_tool_invocations``. Never raises.

    The table is partitioned by ``started_at``; we store the wall-clock
    timestamp so rows land in the correct monthly partition.
    """

    def _write_sync(row: dict[str, Any]) -> None:
        from app.core.database import get_supabase

        sb = get_supabase()
        sb.table("ai_tool_invocations").insert(row).execute()

    started_iso = _epoch_to_iso(invocation.started_at)
    completed_iso = _epoch_to_iso(invocation.started_at + invocation.duration_ms / 1000.0)
    row: dict[str, Any] = {
        "tool_name": invocation.tool_name,
        "agent_name": invocation.agent_name,
        "status": invocation.status,
        "duration_ms": invocation.duration_ms,
        "started_at": started_iso,
        "completed_at": completed_iso,
        "org_id": invocation.org_id,
        "user_id": invocation.user_id,
        "error_message": invocation.error_message,
        "input_hash": invocation.input_hash,
    }
    try:
        await asyncio.to_thread(_write_sync, row)
    except Exception as exc:  # noqa: BLE001 — audit must never block
        logger.warning(
            "tool_registry.audit_write_failed",
            extra={"tool": invocation.tool_name, "status": invocation.status, "error": str(exc)},
        )


def _epoch_to_iso(epoch_seconds: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


__all__ = ["SupabaseToolStore", "supabase_invocation_sink"]
