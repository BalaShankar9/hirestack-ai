"""Per-org cost attribution read service.

P1-8 / m12-pr07. Source of truth = ``public.ai_invocations.cost_cents``;
hot reads served from the ``public.org_cost_hourly`` materialized view
(refreshed every 60s by pg_cron — see migration
``20260509000000_ai_invocations_cost_attribution.sql``).

Two read paths:

* :meth:`get_org_cost_window` — cheap MV scan for "last N hours" charts.
* :meth:`get_org_cost_today_cents` — UTC-day total used by the per-org
  daily $ cap (see m12-pr08).

Tenant identity is taken from authenticated context by callers; never
from untrusted input. The service does not enforce auth; it only reads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.database import get_supabase

logger = logging.getLogger(__name__)


_MV = "org_cost_hourly"
_BASE = "ai_invocations"


class CostAttributionService:
    """Read service over ``org_cost_hourly`` and ``ai_invocations``.

    Stateless; safe to instantiate per-request or reuse a singleton.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client

    def _supabase(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        try:
            return get_supabase()
        except Exception as exc:
            logger.debug("cost_attribution_supabase_unavailable: %s", exc)
            return None

    async def get_org_cost_window(
        self,
        tenant_id: str,
        *,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """Per-tenant cost roll-up for the last ``hours`` hours.

        Reads the materialized view; up to 60s stale. Returns a stable
        shape even when the MV has no rows for this tenant.
        """
        if not tenant_id:
            return self._empty_window(hours)

        sb = self._supabase()
        if sb is None:
            return self._empty_window(hours)

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat()
        try:
            res = (
                sb.table(_MV)
                .select("hour,call_count,total_cost_cents,total_tokens")
                .eq("tenant_id", tenant_id)
                .gte("hour", cutoff)
                .order("hour", desc=False)
                .execute()
            )
            rows: List[Dict[str, Any]] = res.data or []
        except Exception as exc:
            logger.warning(
                "cost_attribution_window_query_failed: tenant=%s err=%s",
                tenant_id, str(exc)[:200],
            )
            return self._empty_window(hours)

        total_cost = sum(int(r.get("total_cost_cents", 0) or 0) for r in rows)
        total_tokens = sum(int(r.get("total_tokens", 0) or 0) for r in rows)
        total_calls = sum(int(r.get("call_count", 0) or 0) for r in rows)

        return {
            "tenant_id": tenant_id,
            "window_hours": hours,
            "total_cost_cents": total_cost,
            "total_tokens": total_tokens,
            "call_count": total_calls,
            "buckets": rows,
            "source": "org_cost_hourly_mv",
        }

    async def get_org_cost_today_cents(self, tenant_id: str) -> int:
        """Sum of ``cost_cents`` for ``tenant_id`` since UTC midnight.

        Reads the base table (not the MV) so the answer is fresh — this
        path feeds the daily $ cap enforcement and must not be lagged
        by the 60s MV refresh window.
        """
        if not tenant_id:
            return 0

        sb = self._supabase()
        if sb is None:
            return 0

        midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).isoformat()
        try:
            res = (
                sb.table(_BASE)
                .select("cost_cents")
                .eq("tenant_id", tenant_id)
                .gte("created_at", midnight)
                .execute()
            )
            rows = res.data or []
        except Exception as exc:
            logger.warning(
                "cost_attribution_today_query_failed: tenant=%s err=%s",
                tenant_id, str(exc)[:200],
            )
            return 0

        return sum(int(r.get("cost_cents", 0) or 0) for r in rows)

    @staticmethod
    def _empty_window(hours: int) -> Dict[str, Any]:
        return {
            "tenant_id": None,
            "window_hours": hours,
            "total_cost_cents": 0,
            "total_tokens": 0,
            "call_count": 0,
            "buckets": [],
            "source": "org_cost_hourly_mv",
        }


_SINGLETON: Optional[CostAttributionService] = None


def get_cost_attribution_service() -> CostAttributionService:
    """Return a process-wide singleton.

    Re-entrant; safe to call from any worker thread.
    """
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = CostAttributionService()
    return _SINGLETON


def _reset_for_tests() -> None:
    """Test helper: drop the singleton."""
    global _SINGLETON
    _SINGLETON = None
