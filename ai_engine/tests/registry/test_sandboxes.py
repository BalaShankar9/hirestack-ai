"""Tests for sandbox tier classifier (ADR-0033, PR m7-pr29)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from ai_engine.registry.sandboxes import (
    L0InProcessSandbox,
    L1HttpxAllowlistSandbox,
    L2GrpcSidecarSandbox,
    SandboxNotImplemented,
    UnknownSandboxTier,
    default_sandboxes,
    select_sandbox,
)
from ai_engine.registry.tools import ToolRecord


def _rec(tier: str = "L0", *, allowlist: list[str] | None = None) -> ToolRecord:
    return ToolRecord(
        name=f"tool-{tier}",
        code_ref="tests.fake",
        sandbox_tier=tier,
        egress_allowlist=allowlist or [],
    )


@pytest.mark.asyncio
async def test_l0_passes_arguments_through() -> None:
    seen: dict[str, Any] = {}

    async def fn(**kw: Any) -> dict:
        seen.update(kw)
        return {"ok": True}

    out = await L0InProcessSandbox().invoke(fn, arguments={"x": 1, "y": 2}, record=_rec())
    assert out == {"ok": True}
    assert seen == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_l1_warns_once_per_tool_then_calls_fn(caplog: pytest.LogCaptureFixture) -> None:
    # Reset class-level dedup so this test is order-independent.
    L1HttpxAllowlistSandbox._warned_tools.clear()
    sb = L1HttpxAllowlistSandbox()
    rec = _rec(tier="L1", allowlist=["api.example.com"])

    async def fn(**_: Any) -> str:
        return "result"

    with caplog.at_level(logging.WARNING):
        out1 = await sb.invoke(fn, arguments={}, record=rec)
        out2 = await sb.invoke(fn, arguments={}, record=rec)

    assert out1 == "result" and out2 == "result"
    warns = [r for r in caplog.records if r.message == "tool_sandbox_l1_unenforced"]
    # Exactly one warning across both calls (dedup by tool name).
    assert len(warns) == 1
    assert getattr(warns[0], "tool", None) == rec.name
    assert getattr(warns[0], "egress_allowlist", None) == ["api.example.com"]


@pytest.mark.asyncio
async def test_l2_raises_with_tool_name() -> None:
    rec = _rec(tier="L2")

    async def fn(**_: Any) -> Any:
        return None

    with pytest.raises(SandboxNotImplemented, match=rec.name):
        await L2GrpcSidecarSandbox().invoke(fn, arguments={}, record=rec)


def test_select_sandbox_flag_off_always_l0_with_shadow_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sandboxes = default_sandboxes()
    rec = _rec(tier="L1")
    with caplog.at_level(logging.INFO):
        sb = select_sandbox(rec, sandboxes, routing_enabled=False)
    assert isinstance(sb, L0InProcessSandbox)
    shadow = [r for r in caplog.records if r.message == "tool_sandbox_shadow"]
    assert len(shadow) == 1
    assert getattr(shadow[0], "declared_tier", None) == "L1"
    assert getattr(shadow[0], "executed_tier", None) == "L0"


def test_select_sandbox_flag_off_no_shadow_when_already_l0(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        sb = select_sandbox(_rec(tier="L0"), default_sandboxes(), routing_enabled=False)
    assert isinstance(sb, L0InProcessSandbox)
    assert not [r for r in caplog.records if r.message == "tool_sandbox_shadow"]


def test_select_sandbox_flag_on_routes_to_declared_tier() -> None:
    sandboxes = default_sandboxes()
    assert isinstance(
        select_sandbox(_rec(tier="L0"), sandboxes, routing_enabled=True),
        L0InProcessSandbox,
    )
    assert isinstance(
        select_sandbox(_rec(tier="L1"), sandboxes, routing_enabled=True),
        L1HttpxAllowlistSandbox,
    )
    assert isinstance(
        select_sandbox(_rec(tier="L2"), sandboxes, routing_enabled=True),
        L2GrpcSidecarSandbox,
    )


def test_select_sandbox_unknown_tier_raises() -> None:
    with pytest.raises(UnknownSandboxTier, match="L3"):
        select_sandbox(_rec(tier="L3"), default_sandboxes(), routing_enabled=True)
    with pytest.raises(UnknownSandboxTier, match="garbage"):
        select_sandbox(_rec(tier="garbage"), default_sandboxes(), routing_enabled=True)
