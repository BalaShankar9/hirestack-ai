"""Tests for ai_engine.cost_breaker (P0-4 / m12-pr08)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_engine import cost_breaker as cb


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ORG_DAILY_COST_CAP_USD", raising=False)
    monkeypatch.delenv("ORG_DAILY_COST_CAP_OVERRIDES", raising=False)
    yield


# ─── ContextVar ─────────────────────────────────────────────────────────


def test_tenant_context_default_none():
    assert cb.get_tenant_id() is None


def test_tenant_context_set_reset():
    token = cb.set_tenant_id("org-1")
    try:
        assert cb.get_tenant_id() == "org-1"
    finally:
        cb.reset_tenant_id(token)
    assert cb.get_tenant_id() is None


def test_tenant_scope_async():
    async def run():
        async with cb.tenant_scope("org-2"):
            assert cb.get_tenant_id() == "org-2"
        assert cb.get_tenant_id() is None
    asyncio.run(run())


# ─── Cap parsing ────────────────────────────────────────────────────────


def test_cap_disabled_when_unset():
    assert cb.cap_cents_for("org-1") is None


def test_global_cap_parsed(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "12.50")
    assert cb.cap_cents_for("org-1") == 1250


def test_global_cap_invalid_string(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "abc")
    assert cb.cap_cents_for("org-1") is None


def test_global_cap_zero_disables(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "0")
    assert cb.cap_cents_for("org-1") is None


def test_per_tenant_override_wins(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")
    monkeypatch.setenv(
        "ORG_DAILY_COST_CAP_OVERRIDES",
        json.dumps({"org-special": 99.0}),
    )
    assert cb.cap_cents_for("org-special") == 9900
    assert cb.cap_cents_for("org-other") == 1000


def test_per_tenant_override_zero_disables(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")
    monkeypatch.setenv(
        "ORG_DAILY_COST_CAP_OVERRIDES",
        json.dumps({"org-vip": 0}),
    )
    assert cb.cap_cents_for("org-vip") is None
    assert cb.cap_cents_for("org-other") == 1000


def test_overrides_invalid_json(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "5")
    monkeypatch.setenv("ORG_DAILY_COST_CAP_OVERRIDES", "not-json")
    assert cb.cap_cents_for("org-1") == 500


# ─── Enforcement ────────────────────────────────────────────────────────


def _patch_cost_service(spent_cents: int) -> MagicMock:
    svc = MagicMock()
    svc.get_org_cost_today_cents = AsyncMock(return_value=spent_cents)
    return svc


@pytest.mark.asyncio
async def test_enforce_no_tenant_is_noop(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "1")
    # No tenant in context, no tenant param → no DB call, no raise.
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service"
    ) as get_svc:
        await cb.enforce_org_daily_cost_cap()
        assert not get_svc.called


@pytest.mark.asyncio
async def test_enforce_no_cap_is_noop(monkeypatch):
    # Tenant bound but no cap configured → no DB call, no raise.
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service"
    ) as get_svc:
        await cb.enforce_org_daily_cost_cap(tenant_id="org-1")
        assert not get_svc.called


@pytest.mark.asyncio
async def test_enforce_under_cap_no_raise(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")  # 1000 cents
    svc = _patch_cost_service(spent_cents=500)
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        await cb.enforce_org_daily_cost_cap(tenant_id="org-1")
    svc.get_org_cost_today_cents.assert_awaited_once_with("org-1")


@pytest.mark.asyncio
async def test_enforce_over_cap_raises(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")  # 1000 cents
    svc = _patch_cost_service(spent_cents=1500)
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        with pytest.raises(cb.OrgDailyCostCapExceeded) as excinfo:
            await cb.enforce_org_daily_cost_cap(tenant_id="org-1")
    assert excinfo.value.tenant_id == "org-1"
    assert excinfo.value.spent_cents == 1500
    assert excinfo.value.cap_cents == 1000


@pytest.mark.asyncio
async def test_enforce_at_exact_cap_raises(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")
    svc = _patch_cost_service(spent_cents=1000)
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        with pytest.raises(cb.OrgDailyCostCapExceeded):
            await cb.enforce_org_daily_cost_cap(tenant_id="org-1")


@pytest.mark.asyncio
async def test_enforce_uses_context_tenant(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")
    svc = _patch_cost_service(spent_cents=2000)
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        async with cb.tenant_scope("org-from-ctx"):
            with pytest.raises(cb.OrgDailyCostCapExceeded) as excinfo:
                await cb.enforce_org_daily_cost_cap()
    assert excinfo.value.tenant_id == "org-from-ctx"
    svc.get_org_cost_today_cents.assert_awaited_once_with("org-from-ctx")


@pytest.mark.asyncio
async def test_enforce_fail_open_on_db_error(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "10")
    svc = MagicMock()
    svc.get_org_cost_today_cents = AsyncMock(
        side_effect=RuntimeError("supabase down"),
    )
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        # Must not raise — fail-open behaviour.
        await cb.enforce_org_daily_cost_cap(tenant_id="org-1")


@pytest.mark.asyncio
async def test_enforce_emits_cap_tripped_event(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "5")
    svc = _patch_cost_service(spent_cents=900)

    emitted: list[tuple[str, dict]] = []

    async def emitter(name, payload):
        emitted.append((name, payload))

    from ai_engine.agent_events import event_emitter_scope
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        with event_emitter_scope(emitter):
            with pytest.raises(cb.OrgDailyCostCapExceeded):
                await cb.enforce_org_daily_cost_cap(tenant_id="org-1")

    assert len(emitted) == 1
    name, payload = emitted[0]
    assert name == "cost.cap.tripped"
    assert payload == {
        "tenant_id": "org-1",
        "spent_cents": 900,
        "cap_cents": 500,
    }


@pytest.mark.asyncio
async def test_enforce_emit_event_disabled(monkeypatch):
    monkeypatch.setenv("ORG_DAILY_COST_CAP_USD", "5")
    svc = _patch_cost_service(spent_cents=900)

    emitted: list[tuple[str, dict]] = []

    async def emitter(name, payload):
        emitted.append((name, payload))

    from ai_engine.agent_events import event_emitter_scope
    with patch(
        "backend.app.services.cost_attribution.get_cost_attribution_service",
        return_value=svc,
    ):
        with event_emitter_scope(emitter):
            with pytest.raises(cb.OrgDailyCostCapExceeded):
                await cb.enforce_org_daily_cost_cap(
                    tenant_id="org-1", emit_event=False,
                )
    assert emitted == []


def test_exception_message_format():
    exc = cb.OrgDailyCostCapExceeded("org-x", 1234, 1000)
    msg = str(exc)
    assert "org-x" in msg
    assert "1234" in msg
    assert "1000" in msg
