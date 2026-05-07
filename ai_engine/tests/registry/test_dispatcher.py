"""Tests for the tool registry dispatcher (PR m5-pr14)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_engine.registry import (
    Dispatcher,
    GrantDenied,
    InvalidInput,
    InvalidOutput,
    RegistryDisabled,
    ToolInvocation,
    ToolNotFound,
    ToolTimeout,
)
from ai_engine.registry.tools import InMemoryToolStore, ToolRecord


def _store(*, granted: bool = True, output_schema: dict | None = None,
           input_schema: dict | None = None, timeout_ms: int = 5_000,
           enabled: bool = True) -> InMemoryToolStore:
    rec = ToolRecord(
        name="echo",
        code_ref="tests.echo",
        input_schema=input_schema or {"type": "object", "required": ["text"],
                                       "properties": {"text": {"type": "string"}}},
        output_schema=output_schema if output_schema is not None else {"type": "object"},
        timeout_ms=timeout_ms,
        enabled=enabled,
    )
    grants: set[tuple[str, str]] = set()
    if granted:
        grants.add(("agent-a", "echo"))
    return InMemoryToolStore(tools={"echo": rec}, grants=grants)


def _make_dispatcher(store, fn, *, enabled: bool = True, sink=None) -> Dispatcher:
    return Dispatcher(
        store=store,
        resolver=lambda _ref: fn,
        sink=sink,
        _enabled_override=enabled,
    )


@pytest.mark.asyncio
async def test_disabled_registry_refuses_dispatch() -> None:
    async def fn(**_: Any) -> dict:
        return {}

    disp = _make_dispatcher(_store(), fn, enabled=False)
    with pytest.raises(RegistryDisabled):
        await disp.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "hi"})


@pytest.mark.asyncio
async def test_unknown_tool_raises_not_found() -> None:
    async def fn(**_: Any) -> dict:
        return {}

    disp = _make_dispatcher(_store(), fn)
    with pytest.raises(ToolNotFound):
        await disp.invoke(tool_name="nope", agent_name="agent-a", arguments={"text": "x"})


@pytest.mark.asyncio
async def test_grant_denied_records_audit() -> None:
    seen: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        seen.append(inv)

    async def fn(**_: Any) -> dict:
        return {}

    disp = _make_dispatcher(_store(granted=False), fn, sink=sink)
    with pytest.raises(GrantDenied):
        await disp.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    assert len(seen) == 1
    assert seen[0].status == "denied"
    assert seen[0].error_message == "grant_denied"


@pytest.mark.asyncio
async def test_invalid_input_caught_before_invoke() -> None:
    calls: list[dict] = []

    async def fn(**kwargs: Any) -> dict:
        calls.append(kwargs)
        return {}

    disp = _make_dispatcher(_store(), fn)
    with pytest.raises(InvalidInput):
        await disp.invoke(tool_name="echo", agent_name="agent-a", arguments={})
    assert calls == []


@pytest.mark.asyncio
async def test_happy_path_runs_and_audits() -> None:
    seen: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        seen.append(inv)

    async def fn(text: str) -> dict:
        return {"echoed": text}

    disp = _make_dispatcher(_store(), fn, sink=sink)
    out = await disp.invoke(tool_name="echo", agent_name="agent-a",
                            arguments={"text": "hello"})
    assert out == {"echoed": "hello"}
    assert len(seen) == 1 and seen[0].status == "ok"
    assert seen[0].input_hash and len(seen[0].input_hash) == 32


@pytest.mark.asyncio
async def test_timeout_surfaces_and_audits() -> None:
    seen: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        seen.append(inv)

    async def fn(**_: Any) -> dict:
        await asyncio.sleep(0.5)
        return {}

    disp = _make_dispatcher(_store(timeout_ms=10), fn, sink=sink)
    with pytest.raises(ToolTimeout):
        await disp.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    assert seen[-1].status == "timeout"


@pytest.mark.asyncio
async def test_invalid_output_caught_after_invoke() -> None:
    async def fn(**_: Any) -> str:
        return "not-an-object"

    disp = _make_dispatcher(_store(), fn)
    with pytest.raises(InvalidOutput):
        await disp.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})


@pytest.mark.asyncio
async def test_tool_exception_and_wildcard_grant() -> None:
    """Wildcard grant works; tool exceptions are audited then re-raised."""
    seen: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        seen.append(inv)

    store = _store(granted=False)
    store.grants.add(("*", "echo"))

    async def fn(**_: Any) -> dict:
        raise RuntimeError("boom")

    disp = _make_dispatcher(store, fn, sink=sink)
    with pytest.raises(RuntimeError):
        await disp.invoke(tool_name="echo", agent_name="random", arguments={"text": "x"})
    assert seen[-1].status == "error" and "boom" in (seen[-1].error_message or "")


def test_seed_rows_are_well_formed() -> None:
    from ai_engine.registry.seed import seed_rows

    tools, grants = seed_rows()
    assert tools and grants
    for tool in tools:
        assert tool["name"] and tool["code_ref"]
        assert isinstance(tool["input_schema"], dict)
    assert all(len(g) == 2 for g in grants)
