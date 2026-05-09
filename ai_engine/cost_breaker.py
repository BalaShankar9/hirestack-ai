"""Per-org daily cost cap + cascade breaker.

P0-4 / m12-pr08. Consumes ``backend.app.services.cost_attribution`` to
short-circuit LLM calls when an org has spent past its configured daily
USD ceiling. Tripped at the entry to the cascade — never inside it —
so a tripped cap costs zero LLM tokens.

Tenant identity is propagated via a :class:`contextvars.ContextVar`
(``set_tenant_id`` / :func:`tenant_scope`). The cap is read from env:

* ``ORG_DAILY_COST_CAP_USD`` — global default (e.g. ``"50"`` = $50/day).
  Empty/unset → cap disabled (open mode).
* ``ORG_DAILY_COST_CAP_OVERRIDES`` — JSON ``{"<tenant_id>": <usd>}`` for
  per-tenant caps. ``0`` disables the cap for that tenant.

Failure modes are conservative: if the cost service can't be reached or
the cap can't be parsed, the cap is **not** enforced (fail-open). This
matches blueprint guidance — a billing telemetry outage must not cause
a service outage.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


_current_tenant_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ai_current_tenant_id", default=None
)


# ─── Tenant context ─────────────────────────────────────────────────────


def set_tenant_id(tenant_id: Optional[str]) -> contextvars.Token:
    """Bind ``tenant_id`` to the current async context. Returns reset token."""
    return _current_tenant_id.set(tenant_id)


def reset_tenant_id(token: contextvars.Token) -> None:
    """Undo a previous :func:`set_tenant_id`."""
    _current_tenant_id.reset(token)


def get_tenant_id() -> Optional[str]:
    """Return the tenant bound to the current context (or ``None``)."""
    return _current_tenant_id.get()


@asynccontextmanager
async def tenant_scope(tenant_id: Optional[str]) -> AsyncIterator[None]:
    """Async context manager that binds a tenant for the enclosed block.

    Use at request entry (HTTP handler, worker job pickup, SSE start)
    so every nested LLM call inherits the tenant without parameter
    drilling.
    """
    token = set_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_tenant_id(token)


# ─── Cap configuration ──────────────────────────────────────────────────


def _parse_global_cap_cents() -> Optional[int]:
    raw = (os.getenv("ORG_DAILY_COST_CAP_USD", "") or "").strip()
    if not raw:
        return None
    try:
        usd = float(raw)
    except ValueError:
        logger.warning("invalid_org_daily_cost_cap_usd: raw=%r", raw)
        return None
    if usd <= 0:
        return None
    return int(round(usd * 100))


def _parse_overrides_cents() -> dict[str, int]:
    raw = (os.getenv("ORG_DAILY_COST_CAP_OVERRIDES", "") or "").strip()
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid_org_daily_cost_cap_overrides: not json")
        return {}
    if not isinstance(decoded, dict):
        return {}
    out: dict[str, int] = {}
    for tid, usd in decoded.items():
        try:
            cents = int(round(float(usd) * 100))
        except (TypeError, ValueError):
            continue
        out[str(tid)] = max(0, cents)
    return out


def cap_cents_for(tenant_id: str) -> Optional[int]:
    """Return the cap (in cents) for ``tenant_id``, or ``None`` if disabled.

    Override semantics:

    * ``tenant_id`` explicitly mapped to ``0`` → cap disabled.
    * ``tenant_id`` mapped to positive cents → that cap applies.
    * Otherwise → fall back to the global env cap.
    """
    overrides = _parse_overrides_cents()
    if tenant_id in overrides:
        cents = overrides[tenant_id]
        return cents if cents > 0 else None
    return _parse_global_cap_cents()


# ─── Exception ──────────────────────────────────────────────────────────


class OrgDailyCostCapExceeded(Exception):
    """Raised when an org's daily LLM spend would exceed its configured cap.

    Carries the numbers so callers / metrics / logs can render a
    meaningful message without re-querying.
    """

    def __init__(self, tenant_id: str, spent_cents: int, cap_cents: int) -> None:
        self.tenant_id = tenant_id
        self.spent_cents = int(spent_cents)
        self.cap_cents = int(cap_cents)
        super().__init__(
            f"org_daily_cost_cap_exceeded: tenant={tenant_id} "
            f"spent_cents={self.spent_cents} cap_cents={self.cap_cents}"
        )


# ─── Enforcement ────────────────────────────────────────────────────────


async def _emit_cap_tripped(tenant_id: str, spent_cents: int, cap_cents: int) -> None:
    """Best-effort emit of ``cost.cap.tripped`` to the bound event emitter."""
    try:
        from ai_engine.agent_events import get_event_emitter
        emitter = get_event_emitter()
        if emitter is None:
            return
        await emitter("cost.cap.tripped", {
            "tenant_id": tenant_id,
            "spent_cents": spent_cents,
            "cap_cents": cap_cents,
        })
    except Exception as exc:
        logger.debug("cost_cap_event_emit_failed: %s", exc)


async def enforce_org_daily_cost_cap(
    tenant_id: Optional[str] = None,
    *,
    emit_event: bool = True,
) -> None:
    """Raise :class:`OrgDailyCostCapExceeded` if the org is over its daily cap.

    No-op when:

    * No tenant is bound and none is passed.
    * No cap is configured for the tenant.
    * The cost service is unavailable (fail-open — telemetry outage
      must not become an availability outage).

    Reads today's spend via
    :class:`backend.app.services.cost_attribution.CostAttributionService`,
    which queries the base ``ai_invocations`` table since UTC midnight
    so the answer is fresh (not bounded by the 60s MV refresh).
    """
    tid = tenant_id or get_tenant_id()
    if not tid:
        return
    cap = cap_cents_for(tid)
    if cap is None:
        return

    try:
        from backend.app.services.cost_attribution import (
            get_cost_attribution_service,
        )
        spent = await get_cost_attribution_service().get_org_cost_today_cents(tid)
    except Exception as exc:
        # Fail-open: telemetry outage must not break the request path.
        logger.warning("cost_cap_check_skipped_due_to_error: tenant=%s err=%s",
                       tid, str(exc)[:200])
        return

    if int(spent) >= int(cap):
        if emit_event:
            await _emit_cap_tripped(tid, int(spent), int(cap))
        logger.warning(
            "org_daily_cost_cap_exceeded: tenant=%s spent_cents=%s cap_cents=%s",
            tid, spent, cap,
        )
        raise OrgDailyCostCapExceeded(tid, int(spent), int(cap))
