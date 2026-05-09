"""Provider-failover guarantee — Must Never Happen scenario §21.

Blueprint guarantee: *"Single Gemini outage takes down platform"* must
**not** be possible. The model_router cascade is the mechanism: when
the entire Gemini family is unhealthy and the Anthropic provider is
enabled, the cascade must surface ``claude-*`` so callers can serve
traffic.

This file is the **scenario-level** contract. Lower-level cascade
mechanics (health threshold, recovery probes, env overrides) are
already locked down in ``backend/tests/unit/test_model_router.py`` —
do not duplicate them here.

Each test is one sentence:

  "Given <state>, the cascade for a Tier-1 task must <outcome>."

That keeps regressions diff-readable.
"""
from __future__ import annotations

import pytest

from ai_engine import model_router


# Tier-1 cascades are the ones with Anthropic at the tail.
TIER1_TASKS = ("reasoning", "fact_checking", "quality_doc")
GEMINI_TIER1_FAMILY = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Hard-reset router singletons + env overrides between tests."""
    model_router.reload_routes()
    model_router._model_health._failures.clear()
    model_router._model_health._last_failure.clear()
    monkeypatch.delenv("MODEL_ROUTES", raising=False)
    monkeypatch.delenv("MODEL_CASCADE", raising=False)
    yield
    model_router.reload_routes()
    model_router._model_health._failures.clear()
    model_router._model_health._last_failure.clear()


def _kill(*models: str) -> None:
    """Mark models unhealthy by exceeding the failure threshold."""
    for m in models:
        for _ in range(model_router._ModelHealth.FAILURE_THRESHOLD):
            model_router.record_model_failure(m)


def _enable_anthropic(monkeypatch) -> None:
    """Force ``ff_anthropic_provider`` ON via settings + env fallback."""
    monkeypatch.setenv("FF_ANTHROPIC_PROVIDER", "1")
    try:
        from app.core.config import settings  # type: ignore
        monkeypatch.setattr(settings, "ff_anthropic_provider", True, raising=False)
    except Exception:
        pass


def _disable_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("FF_ANTHROPIC_PROVIDER", "0")
    try:
        from app.core.config import settings  # type: ignore
        monkeypatch.setattr(settings, "ff_anthropic_provider", False, raising=False)
    except Exception:
        pass


# ── ship-state baseline (Anthropic OFF) ───────────────────────────────


@pytest.mark.parametrize("task", TIER1_TASKS)
def test_anthropic_disabled_strips_claude_from_cascade(monkeypatch, task):
    """Ship state: Anthropic flag OFF → no claude-* in any tier-1 cascade.

    This is the contract that ADR-0031 / m7-pr28 set: the static cascade
    *declares* Anthropic at the tail, but the runtime resolver must
    filter it out unless the flag is ON. Otherwise a misconfigured
    deploy would silently start hitting Anthropic's billing API.
    """
    _disable_anthropic(monkeypatch)
    cascade = model_router.resolve_cascade(task, "gemini-2.5-pro")
    assert all(not m.startswith("claude-") for m in cascade), cascade


# ── flag-ON failover guarantee ────────────────────────────────────────


@pytest.mark.parametrize("task", TIER1_TASKS)
def test_anthropic_enabled_keeps_claude_in_cascade(monkeypatch, task):
    _enable_anthropic(monkeypatch)
    cascade = model_router.resolve_cascade(task, "gemini-2.5-pro")
    assert any(m.startswith("claude-") for m in cascade), cascade


@pytest.mark.parametrize("task", TIER1_TASKS)
def test_full_gemini_outage_surfaces_anthropic(monkeypatch, task):
    """**Must Never Happen scenario**: full Gemini family unhealthy +
    Anthropic enabled → cascade returns the claude entry first.

    If this test ever fails, a Gemini regional outage would take the
    platform down. That is categorically unacceptable per blueprint
    §21. Do not delete or skip this test.
    """
    _enable_anthropic(monkeypatch)
    _kill(*GEMINI_TIER1_FAMILY)

    cascade = model_router.resolve_cascade(task, "gemini-2.5-pro")
    # The healthy-filter must have removed every Gemini entry and left
    # exactly the Anthropic tail.
    assert cascade, "cascade collapsed to empty under all-Gemini outage"
    assert all(m.startswith("claude-") for m in cascade), cascade


@pytest.mark.parametrize("task", TIER1_TASKS)
def test_partial_gemini_outage_falls_through_within_family(monkeypatch, task):
    """Pro down → Flash should still be the next pick (not Anthropic).

    Failover should prefer the cheaper same-provider model before
    crossing to Anthropic, both for cost and for data-residency.
    """
    _enable_anthropic(monkeypatch)
    _kill("gemini-2.5-pro")

    cascade = model_router.resolve_cascade(task, "gemini-2.5-pro")
    assert "gemini-2.5-pro" not in cascade
    assert "gemini-2.5-flash" in cascade
    # Flash must come before claude in the priority list.
    flash_idx = cascade.index("gemini-2.5-flash")
    claude_idx = next(
        (i for i, m in enumerate(cascade) if m.startswith("claude-")), None
    )
    if claude_idx is not None:
        assert flash_idx < claude_idx, cascade


# ── degenerate cases ──────────────────────────────────────────────────


def test_full_outage_with_anthropic_disabled_still_returns_something(monkeypatch):
    """Last-resort path: every Gemini model unhealthy AND Anthropic OFF.

    The router's documented behaviour is "return all (incl. unhealthy)
    so we at least try" — operators see retries instead of a blank
    cascade that would cause callers to KeyError or pick a bogus
    default. Pin that here so a future refactor can't return ``[]``.
    """
    _disable_anthropic(monkeypatch)
    _kill(*GEMINI_TIER1_FAMILY)

    cascade = model_router.resolve_cascade("reasoning", "gemini-2.5-pro")
    assert cascade, "cascade collapsed to empty under full outage"
    # Must be Gemini-only (Anthropic flag is OFF).
    assert all(not m.startswith("claude-") for m in cascade), cascade


def test_anthropic_enabled_recovery_brings_gemini_back(monkeypatch):
    """After RECOVERY_TIMEOUT, a previously-unhealthy Gemini model
    becomes probable again — cascade must return Gemini ahead of
    Anthropic. This is the auto-recovery half of the failover contract."""
    _enable_anthropic(monkeypatch)
    _kill("gemini-2.5-pro")
    h = model_router._model_health
    # Fast-forward the unhealthy-since timestamp past RECOVERY_TIMEOUT.
    h._last_failure["gemini-2.5-pro"] = (
        h._last_failure["gemini-2.5-pro"] - h.RECOVERY_TIMEOUT - 1
    )

    cascade = model_router.resolve_cascade("reasoning", "gemini-2.5-pro")
    assert cascade[0] == "gemini-2.5-pro", cascade


def test_failover_recorded_in_health_status(monkeypatch):
    """The health surface must expose unhealthy models so /metrics and
    runbooks can alert. Without this, a silent failover is invisible."""
    _kill("gemini-2.5-pro")
    status = model_router.get_model_health()
    assert "gemini-2.5-pro" in status
    assert status["gemini-2.5-pro"]["healthy"] is False
    assert (
        status["gemini-2.5-pro"]["failures"]
        >= model_router._ModelHealth.FAILURE_THRESHOLD
    )
