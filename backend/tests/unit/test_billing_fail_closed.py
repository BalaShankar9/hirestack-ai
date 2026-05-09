"""Tests for TD-7 / m12-pr11 billing fail-closed behaviour."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import deps


# ── _billing_fail_closed_enabled ──────────────────────────────────────


def test_default_dev_is_fail_open(monkeypatch):
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert deps._billing_fail_closed_enabled() is False


def test_production_default_is_fail_closed(monkeypatch):
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert deps._billing_fail_closed_enabled() is True


def test_env_override_forces_fail_closed_in_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BILLING_FAIL_CLOSED", "1")
    assert deps._billing_fail_closed_enabled() is True


def test_env_override_forces_fail_open_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BILLING_FAIL_CLOSED", "0")
    assert deps._billing_fail_closed_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "Yes", "on"])
def test_env_truthy_variants(monkeypatch, truthy):
    monkeypatch.setenv("BILLING_FAIL_CLOSED", truthy)
    assert deps._billing_fail_closed_enabled() is True


@pytest.mark.parametrize("falsy", ["0", "false", "no", "off", ""])
def test_env_falsy_variants(monkeypatch, falsy):
    monkeypatch.setenv("BILLING_FAIL_CLOSED", falsy)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert deps._billing_fail_closed_enabled() is False


# ── check_billing_limit org-fetch failure path ────────────────────────


class _FakeOrgService:
    def __init__(self, *, orgs=None, raises=None):
        self._orgs = orgs or []
        self._raises = raises

    async def get_user_orgs(self, user_id):
        if self._raises is not None:
            raise self._raises
        return self._orgs


class _FakeBillingService:
    def __init__(self, allowed=True, raises=None):
        self._allowed = allowed
        self._raises = raises

    async def check_limit(self, org_id, feature):
        if self._raises is not None:
            raise self._raises
        return self._allowed


@pytest.fixture
def patch_services(monkeypatch):
    """Patch OrgService / BillingService imports inside check_billing_limit."""
    state = {"org": _FakeOrgService(), "billing": _FakeBillingService()}

    import app.services.org as org_mod
    import app.services.billing as billing_mod

    monkeypatch.setattr(org_mod, "OrgService", lambda: state["org"])
    monkeypatch.setattr(billing_mod, "BillingService", lambda: state["billing"])
    return state


@pytest.mark.asyncio
async def test_org_fetch_failure_fails_open_in_dev(monkeypatch, patch_services):
    """Legacy permissive path: dev/test envs swallow the error."""
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    patch_services["org"] = _FakeOrgService(raises=RuntimeError("supabase down"))

    # Should silently return (no orgs → skip enforcement).
    await deps.check_billing_limit("resume_generation", {"id": "user-1"})


@pytest.mark.asyncio
async def test_org_fetch_failure_fails_closed_in_production(
    monkeypatch, patch_services
):
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    patch_services["org"] = _FakeOrgService(raises=RuntimeError("supabase down"))

    with pytest.raises(HTTPException) as exc:
        await deps.check_billing_limit("resume_generation", {"id": "user-1"})
    assert exc.value.status_code == 503
    assert "Billing service" in exc.value.detail


@pytest.mark.asyncio
async def test_org_fetch_failure_fails_closed_when_env_override(
    monkeypatch, patch_services
):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("BILLING_FAIL_CLOSED", "1")
    patch_services["org"] = _FakeOrgService(raises=RuntimeError("boom"))

    with pytest.raises(HTTPException) as exc:
        await deps.check_billing_limit("resume_generation", {"id": "user-1"})
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_org_fetch_failure_fails_open_when_override_off(
    monkeypatch, patch_services
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BILLING_FAIL_CLOSED", "0")
    patch_services["org"] = _FakeOrgService(raises=RuntimeError("boom"))

    # Override forces fail-open even in production — should not raise.
    await deps.check_billing_limit("resume_generation", {"id": "user-1"})


@pytest.mark.asyncio
async def test_no_orgs_skips_enforcement(monkeypatch, patch_services):
    """Genuine no-org user (solo mode) is unaffected by fail-closed mode."""
    monkeypatch.setenv("BILLING_FAIL_CLOSED", "1")
    patch_services["org"] = _FakeOrgService(orgs=[])
    # Should return cleanly — no org → skip.
    await deps.check_billing_limit("resume_generation", {"id": "user-1"})


@pytest.mark.asyncio
async def test_org_present_then_billing_check_failure_still_503(
    monkeypatch, patch_services
):
    """Pre-existing 503 path on billing.check_limit() error is preserved."""
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    patch_services["org"] = _FakeOrgService(orgs=[{"id": "org-1"}])
    patch_services["billing"] = _FakeBillingService(raises=RuntimeError("billing down"))

    with pytest.raises(HTTPException) as exc:
        await deps.check_billing_limit("resume_generation", {"id": "user-1"})
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_org_present_and_allowed_passes(monkeypatch, patch_services):
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    patch_services["org"] = _FakeOrgService(orgs=[{"id": "org-1"}])
    patch_services["billing"] = _FakeBillingService(allowed=True)
    await deps.check_billing_limit("resume_generation", {"id": "user-1"})


@pytest.mark.asyncio
async def test_org_present_and_denied_raises_402(monkeypatch, patch_services):
    monkeypatch.delenv("BILLING_FAIL_CLOSED", raising=False)
    patch_services["org"] = _FakeOrgService(orgs=[{"id": "org-1"}])
    patch_services["billing"] = _FakeBillingService(allowed=False)

    with pytest.raises(HTTPException) as exc:
        await deps.check_billing_limit("resume_generation", {"id": "user-1"})
    assert exc.value.status_code == 402
