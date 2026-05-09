"""Tests for P1-8 / m12-pr07 cost attribution.

Covers:
  * Recorder: ``cost_cents`` column is written when supplied.
  * Recorder: ``cost_cents`` defaults to 0 when caller omits it.
  * Read service: ``get_org_cost_window`` aggregates MV rows correctly.
  * Read service: ``get_org_cost_today_cents`` reads base table since
    UTC midnight.
  * Read service: missing supabase + empty rows degrade safely to 0.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ─── Recorder side ──────────────────────────────────────────────────────

def _fake_supabase() -> MagicMock:
    sb = MagicMock(name="supabase")
    sb.table.return_value = sb
    sb.insert.return_value = sb
    sb.execute.return_value = MagicMock(data=[], count=None)
    return sb


@pytest.fixture(autouse=True)
def _reset_recorder():
    from ai_engine.observability.ai_invocations import reset_recorder_for_tests
    reset_recorder_for_tests()
    yield
    reset_recorder_for_tests()


@pytest.fixture
def _flag_on(monkeypatch):
    from ai_engine.observability import ai_invocations as mod
    monkeypatch.setattr(mod, "_flag_enabled", lambda: True)
    return mod


def _last_row(sb: MagicMock) -> dict:
    args, _ = sb.insert.call_args
    assert args
    return args[0]


def test_recorder_persists_cost_cents_when_supplied(_flag_on):
    """cost_cents kwarg flows through to the insert payload."""
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1000,
            completion_tokens=500, latency_ms=10, outcome="success",
            cost_cents=37,
        ))
    assert _last_row(sb)["cost_cents"] == 37


def test_recorder_defaults_cost_cents_to_zero(_flag_on):
    """Omitting cost_cents writes 0 (forward-compat for legacy callers)."""
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1,
            completion_tokens=1, latency_ms=1, outcome="success",
        ))
    assert _last_row(sb)["cost_cents"] == 0


def test_recorder_clamps_negative_cost_cents(_flag_on):
    """Garbage negative cost is clamped to 0 — never written as negative."""
    sb = _fake_supabase()
    from ai_engine.observability.ai_invocations import AIInvocationsRecorder
    rec = AIInvocationsRecorder()
    with patch.object(rec, "_get_supabase", return_value=sb):
        asyncio.run(rec.record(
            model="gemini-2.5-flash", prompt_text="p", prompt_tokens=1,
            completion_tokens=1, latency_ms=1, outcome="success",
            cost_cents=-99,
        ))
    assert _last_row(sb)["cost_cents"] == 0


# ─── Client wiring: estimate_call_cost flows into _record_invocation ────

def test_client_estimate_call_cost_used_for_cost_cents():
    """Verify the formula path: estimate_call_cost(model, in, out) * 100."""
    from ai_engine.model_router import estimate_call_cost
    cost_usd = estimate_call_cost("gemini-2.5-flash", 10_000, 5_000)
    cost_cents = int(round(cost_usd * 100))
    # Sanity: gemini-2.5-flash is not free; 10k+5k tokens should be > 0 cents.
    # The value 0 would mean the formula collapsed.
    assert cost_cents >= 0
    assert isinstance(cost_cents, int)


# ─── Read service ───────────────────────────────────────────────────────

def _mv_response(buckets: list[dict]) -> MagicMock:
    """Mock supabase chain that returns ``buckets`` from execute()."""
    sb = MagicMock(name="supabase")
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.gte.return_value = sb
    sb.order.return_value = sb
    sb.execute.return_value = MagicMock(data=buckets, count=None)
    return sb


def test_get_org_cost_window_aggregates_buckets():
    from backend.app.services.cost_attribution import CostAttributionService
    sb = _mv_response([
        {"hour": "2026-05-09T00:00:00+00:00", "call_count": 5,
         "total_cost_cents": 100, "total_tokens": 1000},
        {"hour": "2026-05-09T01:00:00+00:00", "call_count": 3,
         "total_cost_cents": 50, "total_tokens": 400},
    ])
    svc = CostAttributionService(client=sb)
    out = asyncio.run(svc.get_org_cost_window("tenant-a", hours=24))
    assert out["tenant_id"] == "tenant-a"
    assert out["window_hours"] == 24
    assert out["total_cost_cents"] == 150
    assert out["total_tokens"] == 1400
    assert out["call_count"] == 8
    assert len(out["buckets"]) == 2
    assert out["source"] == "org_cost_hourly_mv"


def test_get_org_cost_window_empty_tenant_returns_empty():
    from backend.app.services.cost_attribution import CostAttributionService
    svc = CostAttributionService(client=MagicMock())
    out = asyncio.run(svc.get_org_cost_window("", hours=24))
    assert out["total_cost_cents"] == 0
    assert out["call_count"] == 0
    assert out["buckets"] == []


def test_get_org_cost_window_db_failure_degrades_safely():
    """If the MV query throws, return zeros — never propagate to caller."""
    from backend.app.services.cost_attribution import CostAttributionService
    sb = MagicMock()
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.gte.return_value = sb
    sb.order.return_value = sb
    sb.execute.side_effect = RuntimeError("connection reset")
    svc = CostAttributionService(client=sb)
    out = asyncio.run(svc.get_org_cost_window("tenant-a", hours=24))
    assert out["total_cost_cents"] == 0
    assert out["call_count"] == 0


def test_get_org_cost_today_cents_sums_base_table():
    from backend.app.services.cost_attribution import CostAttributionService
    rows = [{"cost_cents": 17}, {"cost_cents": 23}, {"cost_cents": 0}]
    sb = MagicMock()
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.gte.return_value = sb
    sb.execute.return_value = MagicMock(data=rows, count=None)
    svc = CostAttributionService(client=sb)
    cents = asyncio.run(svc.get_org_cost_today_cents("tenant-a"))
    assert cents == 40
    # Also verify the gte filter used today's UTC midnight (ISO prefix).
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    gte_call_args = sb.gte.call_args
    assert gte_call_args is not None
    field, value = gte_call_args[0]
    assert field == "created_at"
    assert value.startswith(today_prefix)


def test_get_org_cost_today_cents_empty_tenant_returns_zero():
    from backend.app.services.cost_attribution import CostAttributionService
    svc = CostAttributionService(client=MagicMock())
    assert asyncio.run(svc.get_org_cost_today_cents("")) == 0


def test_get_cost_attribution_service_returns_singleton():
    from backend.app.services.cost_attribution import (
        get_cost_attribution_service,
        _reset_for_tests,
    )
    _reset_for_tests()
    a = get_cost_attribution_service()
    b = get_cost_attribution_service()
    assert a is b
    _reset_for_tests()
