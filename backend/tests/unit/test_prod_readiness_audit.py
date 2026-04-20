"""Production-readiness re-audit: circuit breaker wiring + Stripe idempotency."""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Circuit breaker is actually wired into AIClient hot path ──────────

def test_gemini_provider_invokes_circuit_breaker() -> None:
    """The breaker was imported but never called — regression guard.

    `_generate_content_throttled` is the single chokepoint for Gemini
    SDK calls. It MUST gate the SDK call through `_get_model_breaker`
    so a fully-down provider fast-fails instead of cascading.
    """
    from ai_engine import client as ai_client
    src = inspect.getsource(ai_client._GeminiProvider._generate_content_throttled)
    assert "_get_model_breaker" in src, "breaker must be invoked, not just imported"
    assert "async with _breaker" in src or "async with breaker" in src.lower(), \
        "breaker must gate the SDK call via async-with"


def test_circuit_breaker_per_model_naming() -> None:
    """Each Gemini model gets its own breaker so quota on one doesn't trip another."""
    from ai_engine.client import _get_model_breaker
    b1 = _get_model_breaker("gemini-2.5-pro")
    b2 = _get_model_breaker("gemini-2.5-flash")
    assert b1.name != b2.name
    assert "pro" in b1.name and "ai_model_" in b1.name
    assert "flash" in b2.name and "ai_model_" in b2.name


# ── Stripe webhook idempotency ────────────────────────────────────────

def test_webhook_idempotency_table_registered() -> None:
    from app.core.database import TABLES
    assert TABLES["processed_webhook_events"] == "processed_webhook_events"


def test_webhook_idempotency_migration_exists() -> None:
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    mig = repo_root / "database" / "migrations" / "20260420_stripe_webhook_idempotency.sql"
    assert mig.exists(), f"missing migration: {mig}"
    sql = mig.read_text()
    assert "processed_webhook_events" in sql
    assert "PRIMARY KEY" in sql, "PK on event_id is the actual idempotency mechanism"
    assert "event_id" in sql


@pytest.mark.asyncio
async def test_webhook_handler_skips_duplicate_event() -> None:
    """Already-processed event_id → no side effects."""
    from app.services.billing import BillingService
    svc = BillingService()
    svc.db = MagicMock()
    svc.db.get = AsyncMock(return_value={"event_id": "evt_123"})  # already processed
    svc.db.create = AsyncMock()
    activate = AsyncMock()
    svc._activate_subscription = activate

    await svc.handle_webhook("checkout.session.completed", {
        "id": "evt_123",
        "metadata": {"org_id": "org_1", "plan": "pro"},
        "subscription": "sub_1",
    })
    activate.assert_not_called()
    svc.db.create.assert_not_called()  # no new ledger row either


@pytest.mark.asyncio
async def test_webhook_handler_records_new_event_then_processes() -> None:
    """Fresh event_id → ledger insert THEN side effect runs."""
    from app.services.billing import BillingService
    svc = BillingService()
    svc.db = MagicMock()
    svc.db.get = AsyncMock(return_value=None)
    svc.db.create = AsyncMock()
    svc.get_subscription = AsyncMock(return_value=None)
    activate = AsyncMock()
    svc._activate_subscription = activate

    await svc.handle_webhook("checkout.session.completed", {
        "id": "evt_999",
        "metadata": {"org_id": "org_1", "plan": "pro"},
        "subscription": "sub_1",
    })
    # Ledger row written first, then activation
    svc.db.create.assert_called_once()
    create_args = svc.db.create.call_args
    assert create_args[0][0] == "processed_webhook_events"
    assert create_args[0][1]["event_id"] == "evt_999"
    activate.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_handler_treats_duplicate_insert_as_already_processed() -> None:
    """Two workers race; PK violation on the second → bail without side effect."""
    from app.services.billing import BillingService
    svc = BillingService()
    svc.db = MagicMock()
    svc.db.get = AsyncMock(return_value=None)
    svc.db.create = AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))
    activate = AsyncMock()
    svc._activate_subscription = activate

    await svc.handle_webhook("checkout.session.completed", {
        "id": "evt_race",
        "metadata": {"org_id": "org_1", "plan": "pro"},
        "subscription": "sub_1",
    })
    activate.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_handler_falls_through_on_ledger_failure() -> None:
    """Ledger table missing entirely → log + fall through to legacy guard.

    Better to risk a duplicate than to silently drop a payment event.
    """
    from app.services.billing import BillingService
    svc = BillingService()
    svc.db = MagicMock()
    svc.db.get = AsyncMock(side_effect=Exception("relation does not exist"))
    svc.db.create = AsyncMock()
    svc.get_subscription = AsyncMock(return_value=None)
    activate = AsyncMock()
    svc._activate_subscription = activate

    await svc.handle_webhook("checkout.session.completed", {
        "id": "evt_no_ledger",
        "metadata": {"org_id": "org_1", "plan": "pro"},
        "subscription": "sub_1",
    })
    # Activation still runs — graceful degradation, not silent drop.
    activate.assert_called_once()
