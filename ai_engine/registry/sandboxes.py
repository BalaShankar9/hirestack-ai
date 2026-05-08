"""Tool sandbox tier classifier (ADR-0033, PR m7-pr29).

Three tiers ship in m7-pr29:

* ``L0InProcessSandbox`` — current behaviour. Calls the resolver
  directly. Default for every existing tool.
* ``L1HttpxAllowlistSandbox`` — dispatch path only. Routes the call
  through L0 but logs ``tool_sandbox_l1_unenforced`` so operators see
  the gap. Real httpx host-blocking lands in m7-pr29b once the first
  L1 tool exists; recording the wire here keeps the DB column honest.
* ``L2GrpcSidecarSandbox`` — stub. Raises ``NotImplementedError`` with
  the tool name in the message so any premature L2 assignment is loud.

L3 (Firecracker BYO) is reserved at the schema level only.

Routing is gated by ``ff_tool_sandbox_tier_routing`` (default OFF).
With the flag OFF every dispatch goes through L0 regardless of
``record.sandbox_tier`` — tier is shadow-logged.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, Mapping, Protocol

from .tools import ToolRecord

logger = logging.getLogger(__name__)


# ── exceptions ─────────────────────────────────────────────────────────


class SandboxNotImplemented(NotImplementedError):
    """Raised when a tool is assigned a tier that has no runtime yet."""


class UnknownSandboxTier(ValueError):
    """Tool's sandbox_tier is not one of L0/L1/L2/L3."""


# ── protocol ───────────────────────────────────────────────────────────


class Sandbox(Protocol):
    async def invoke(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> Any: ...


# ── implementations ────────────────────────────────────────────────────


class L0InProcessSandbox:
    """Direct call. Default for every existing tool."""

    async def invoke(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> Any:
        return await fn(**arguments)


class L1HttpxAllowlistSandbox:
    """Dispatch path only — actual host-blocking lands in m7-pr29b.

    The L1 contract (egress allowlist) requires a per-tool httpx client
    that 403s any host not in ``record.egress_allowlist``. Building that
    against zero callers ships speculative scaffolding (zero seeded
    L1 tools today). This class:

    * Logs ``tool_sandbox_l1_unenforced`` once per process per tool so
      the gap is visible without spamming.
    * Calls the resolver directly (L0 semantics).

    When the first real L1 tool lands in ``seed.py``, m7-pr29b replaces
    this with the real httpx-transport interceptor.
    """

    _warned_tools: set[str] = set()

    async def invoke(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> Any:
        if record.name not in self._warned_tools:
            logger.warning(
                "tool_sandbox_l1_unenforced",
                extra={
                    "tool": record.name,
                    "egress_allowlist": list(record.egress_allowlist),
                    "next_step": "m7-pr29b ships real host blocking",
                },
            )
            self._warned_tools.add(record.name)
        return await fn(**arguments)


class L2GrpcSidecarSandbox:
    """Stub. Raises with the tool name so premature L2 assignment is loud."""

    async def invoke(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> Any:
        raise SandboxNotImplemented(
            f"L2 tool-runner sidecar not yet implemented (tool={record.name}); "
            "tracked in M11."
        )


# ── routing ────────────────────────────────────────────────────────────


def default_sandboxes() -> Mapping[str, Sandbox]:
    """Tier-string → sandbox instance. Module-level singletons; cheap."""
    return _DEFAULT_SANDBOXES


_DEFAULT_SANDBOXES: dict[str, Sandbox] = {
    "L0": L0InProcessSandbox(),
    "L1": L1HttpxAllowlistSandbox(),
    "L2": L2GrpcSidecarSandbox(),
    # L3 deliberately absent — assigning it raises UnknownSandboxTier
    # until the marketplace ADR ships.
}


def select_sandbox(
    record: ToolRecord,
    sandboxes: Mapping[str, Sandbox],
    *,
    routing_enabled: bool,
) -> Sandbox:
    """Pick the right sandbox for ``record``.

    With ``routing_enabled=False``, always returns L0 — but logs
    ``tool_sandbox_routed`` so the chosen-vs-actual gap is visible
    in shadow.
    """
    declared = record.sandbox_tier or "L0"
    if not routing_enabled:
        if declared != "L0":
            logger.info(
                "tool_sandbox_shadow",
                extra={"tool": record.name, "declared_tier": declared, "executed_tier": "L0"},
            )
        return sandboxes["L0"]

    sb = sandboxes.get(declared)
    if sb is None:
        raise UnknownSandboxTier(f"{record.name}: unknown sandbox_tier={declared!r}")
    logger.info(
        "tool_sandbox_routed",
        extra={"tool": record.name, "tier": declared},
    )
    return sb


def is_routing_enabled() -> bool:
    """Feature-flag gate. Default OFF."""
    return os.getenv("FF_TOOL_SANDBOX_TIER_ROUTING", "0").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


__all__ = [
    "L0InProcessSandbox",
    "L1HttpxAllowlistSandbox",
    "L2GrpcSidecarSandbox",
    "Sandbox",
    "SandboxNotImplemented",
    "UnknownSandboxTier",
    "default_sandboxes",
    "is_routing_enabled",
    "select_sandbox",
]
