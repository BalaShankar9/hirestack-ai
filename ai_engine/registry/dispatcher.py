"""Tool dispatcher (PR m5-pr14).

Pipeline: lookup → grant check → input validation → invoke (timeout) →
output validation → persist invocation. Uses a tiny built-in validator
(``type``, ``required``, ``properties``) to avoid a jsonschema dep.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional

from .capability import Authorizer, CapabilityInvalid
from .sandboxes import (
    Sandbox,
    UnknownSandboxTier,
    default_sandboxes,
    is_routing_enabled,
    select_sandbox,
)
from .tools import ToolRecord, ToolStore, is_enabled


class RegistryDisabled(RuntimeError):
    """Raised when ff_tool_registry is off."""


class ToolNotFound(LookupError):
    pass


class GrantDenied(PermissionError):
    pass


class CapabilityRequired(GrantDenied):
    """Tool requires a capability token but none was supplied (or invalid)."""


class InvalidInput(ValueError):
    pass


class InvalidOutput(ValueError):
    pass


class ToolTimeout(TimeoutError):
    pass


@dataclass
class ToolInvocation:
    tool_name: str
    agent_name: str
    status: str
    duration_ms: int
    started_at: float
    org_id: Optional[str] = None
    user_id: Optional[str] = None
    error_message: Optional[str] = None
    input_hash: Optional[str] = None
    output: Any = None


# ── tiny validator ──────────────────────────────────────────────────────
_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


def _validate(value: Any, schema: dict[str, Any]) -> Optional[str]:
    if not schema:
        return None
    expected = schema.get("type")
    if expected:
        py = _PY_TYPES.get(expected)
        if py and not isinstance(value, py):
            return f"expected {expected}, got {type(value).__name__}"
        # bool is a subtype of int; keep them apart
        if expected == "integer" and isinstance(value, bool):
            return "expected integer, got boolean"
    if expected == "object" and isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"missing required key: {key}"
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                err = _validate(value[key], subschema)
                if err:
                    return f"{key}: {err}"
    return None


# ── dispatcher ──────────────────────────────────────────────────────────
def _capability_flag_on() -> bool:
    return os.getenv("FF_TOOL_CAPABILITY_TOKENS", "0").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@dataclass
class Dispatcher:
    """Execute a tool through the full registry pipeline."""

    store: ToolStore
    resolver: Callable[[str], Callable[..., Awaitable[Any]]]
    sink: Optional[Callable[[ToolInvocation], Awaitable[None]]] = None
    authorizer: Optional[Authorizer] = None
    sandboxes: Optional[Mapping[str, Sandbox]] = None
    _enabled_override: Optional[bool] = field(default=None, repr=False)

    async def invoke(
        self,
        *,
        tool_name: str,
        agent_name: str,
        arguments: dict[str, Any],
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
        capability_token: Optional[str] = None,
    ) -> Any:
        enabled = self._enabled_override if self._enabled_override is not None else is_enabled()
        if not enabled:
            raise RegistryDisabled("ff_tool_registry is off")

        record = await self.store.get(tool_name)
        if record is None:
            raise ToolNotFound(tool_name)

        if not await self.store.has_grant(agent_name, tool_name):
            await self._record(_invocation(tool_name, agent_name, "denied", 0,
                                          org_id=org_id, user_id=user_id,
                                          error_message="grant_denied"))
            raise GrantDenied(f"{agent_name} not granted {tool_name}")

        # Capability token check (ADR-0032).
        # Two trigger paths:
        #   1) per-tool kill-switch: record.requires_capability_token=True
        #      always demands a valid token regardless of the flag
        #   2) the global flag enables enforcement for tools that ask
        # When neither applies, the token (if any) is ignored.
        flag_on = _capability_flag_on()
        if record.requires_capability_token or (flag_on and capability_token is not None):
            if self.authorizer is None:
                await self._record(_invocation(tool_name, agent_name, "denied", 0,
                                              org_id=org_id, user_id=user_id,
                                              error_message="capability_authorizer_unset"))
                raise CapabilityRequired(f"{tool_name}: no authorizer configured")
            if not capability_token:
                await self._record(_invocation(tool_name, agent_name, "denied", 0,
                                              org_id=org_id, user_id=user_id,
                                              error_message="capability_token_missing"))
                raise CapabilityRequired(f"{tool_name}: capability token required")
            try:
                await self.authorizer.verify(
                    capability_token,
                    tool_name=tool_name,
                    org_id=org_id,
                    user_id=user_id,
                )
            except CapabilityInvalid as exc:
                await self._record(_invocation(tool_name, agent_name, "denied", 0,
                                              org_id=org_id, user_id=user_id,
                                              error_message=f"capability_{exc}"))
                raise CapabilityRequired(f"{tool_name}: {exc}") from exc

        err = _validate(arguments, record.input_schema)
        if err:
            await self._record(_invocation(tool_name, agent_name, "invalid_input", 0,
                                          org_id=org_id, user_id=user_id,
                                          error_message=err))
            raise InvalidInput(err)

        input_hash = _hash(arguments)
        fn = self.resolver(record.code_ref)
        # Sandbox routing (ADR-0033). Flag OFF → always L0 (with shadow log).
        sandboxes = self.sandboxes if self.sandboxes is not None else default_sandboxes()
        try:
            sandbox = select_sandbox(record, sandboxes, routing_enabled=is_routing_enabled())
        except UnknownSandboxTier as exc:
            await self._record(_invocation(tool_name, agent_name, "error", 0,
                                          org_id=org_id, user_id=user_id,
                                          input_hash=input_hash,
                                          error_message=str(exc)))
            raise

        timeout_s = max(0.001, record.timeout_ms / 1000.0)
        started = time.monotonic()
        try:
            output = await asyncio.wait_for(
                sandbox.invoke(fn, arguments=arguments, record=record),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            duration = int((time.monotonic() - started) * 1000)
            await self._record(_invocation(tool_name, agent_name, "timeout", duration,
                                          org_id=org_id, user_id=user_id,
                                          input_hash=input_hash,
                                          error_message=f"timeout_after_{record.timeout_ms}ms"))
            raise ToolTimeout(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — caller decides what to retry
            duration = int((time.monotonic() - started) * 1000)
            await self._record(_invocation(tool_name, agent_name, "error", duration,
                                          org_id=org_id, user_id=user_id,
                                          input_hash=input_hash,
                                          error_message=str(exc)[:500]))
            raise

        duration = int((time.monotonic() - started) * 1000)
        out_err = _validate(output, record.output_schema)
        if out_err:
            await self._record(_invocation(tool_name, agent_name, "invalid_output", duration,
                                          org_id=org_id, user_id=user_id,
                                          input_hash=input_hash,
                                          error_message=out_err))
            raise InvalidOutput(out_err)

        invocation = _invocation(tool_name, agent_name, "ok", duration,
                                 org_id=org_id, user_id=user_id,
                                 input_hash=input_hash)
        invocation.output = output
        await self._record(invocation)
        return output

    async def _record(self, invocation: ToolInvocation) -> None:
        if self.sink is None:
            return
        try:
            await self.sink(invocation)
        except Exception:  # noqa: BLE001 — never let audit failure mask the tool
            pass


def _invocation(tool: str, agent: str, status: str, duration: int, **kwargs: Any) -> ToolInvocation:
    return ToolInvocation(
        tool_name=tool,
        agent_name=agent,
        status=status,
        duration_ms=duration,
        started_at=time.time(),
        **kwargs,
    )


def _hash(arguments: dict[str, Any]) -> str:
    payload = json.dumps(arguments, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
