"""Billing feature-flag tests.

Pin the contract that the billing surface is OFF by default and that the
write endpoints (checkout / portal / webhook) hard-fail with 503 unless
BILLING_ENABLED is explicitly set. Without this the platform could
accept charges before Stripe is wired."""
from __future__ import annotations

import importlib
import os


def _reload_billing_route():
    """Reimport the route module so the feature-flag closure picks up the
    current environment."""
    from backend.app.api.routes import billing as billing_route
    return importlib.reload(billing_route)


def test_billing_disabled_by_default(monkeypatch):
    """Fresh deployment must NOT expose the Stripe surface accidentally."""
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    mod = _reload_billing_route()
    assert mod._billing_enabled() is False, (
        "Billing must be off by default. Setting it on must be an "
        "explicit deployment decision."
    )


def test_billing_enabled_when_truthy(monkeypatch):
    for val in ("true", "1", "yes", "on", "TRUE"):
        monkeypatch.setenv("BILLING_ENABLED", val)
        mod = _reload_billing_route()
        assert mod._billing_enabled() is True, f"value {val!r} should enable billing"


def test_billing_disabled_when_falsy(monkeypatch):
    for val in ("false", "0", "no", "off", ""):
        monkeypatch.setenv("BILLING_ENABLED", val)
        mod = _reload_billing_route()
        assert mod._billing_enabled() is False, f"value {val!r} should disable billing"


def test_require_billing_enabled_raises_503_when_off(monkeypatch):
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    mod = _reload_billing_route()
    from fastapi import HTTPException
    import pytest as _pytest

    with _pytest.raises(HTTPException) as exc:
        mod._require_billing_enabled()
    assert exc.value.status_code == 503, (
        "Billing endpoints must return 503 when the feature flag is off."
    )
    assert "disabled" in str(exc.value.detail).lower(), (
        "The 503 detail must clearly state billing is disabled so the "
        "frontend can render the right empty state."
    )


def test_status_endpoint_returns_billing_disabled_marker(monkeypatch):
    """When billing is off the /status endpoint returns a permissive
    'billing_disabled' plan so dashboards keep working without 503s."""
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    import inspect
    mod = _reload_billing_route()
    src = inspect.getsource(mod)
    assert '"billing_disabled"' in src, (
        "/status must include the billing_disabled marker so the UI "
        "can show 'Beta — billing not configured'."
    )
    assert '"billing_enabled": False' in src, (
        "/status response must include billing_enabled: False so the "
        "frontend can branch on a typed flag, not on plan-name strings."
    )


def test_write_endpoints_call_require_billing_enabled():
    """All Stripe-mutating endpoints must short-circuit on the flag.
    This is a structural test — it inspects the source so the gate
    cannot be silently removed."""
    import inspect
    mod = _reload_billing_route()
    src = inspect.getsource(mod)

    # Each handler must call the gate at least once.
    for handler in ("create_checkout", "create_portal", "stripe_webhook"):
        # Slice the source to the handler block (simple but reliable).
        idx = src.find(f"async def {handler}(")
        assert idx >= 0, f"handler {handler} missing"
        block = src[idx : idx + 1200]
        assert "_require_billing_enabled()" in block, (
            f"{handler} must call _require_billing_enabled() before "
            f"touching Stripe or org state."
        )
