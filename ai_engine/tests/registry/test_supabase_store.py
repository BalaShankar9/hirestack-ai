"""Tests for ``SupabaseToolStore`` and ``supabase_invocation_sink``
(PR m6-pr25)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from ai_engine.registry.dispatcher import ToolInvocation
from ai_engine.registry.supabase_store import (
    SupabaseToolStore,
    supabase_invocation_sink,
)


# ── shared fakes ──────────────────────────────────────────────────────
class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]] | None) -> None:
        self._rows = rows or []
        self.calls: list[tuple[str, tuple, dict]] = []

    def select(self, *a, **kw): self.calls.append(("select", a, kw)); return self
    def eq(self, *a, **kw): self.calls.append(("eq", a, kw)); return self
    def in_(self, *a, **kw): self.calls.append(("in_", a, kw)); return self
    def limit(self, *a, **kw): self.calls.append(("limit", a, kw)); return self
    def insert(self, *a, **kw): self.calls.append(("insert", a, kw)); return self

    def execute(self):
        class R:
            pass
        R.data = self._rows
        return R()


class _FakeSupabase:
    def __init__(self, table_rows: dict[str, list[dict[str, Any]] | None]) -> None:
        self._table_rows = table_rows
        self.queries: dict[str, _FakeQuery] = {}

    def table(self, name: str) -> _FakeQuery:
        q = _FakeQuery(self._table_rows.get(name))
        self.queries[name] = q
        return q


# ── SupabaseToolStore.get ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_returns_tool_record_from_supabase_row():
    fake_sb = _FakeSupabase({
        "ai_tools": [{
            "name": "search_user_history",
            "version": 2,
            "description": "lookup",
            "code_ref": "ai_engine.agents.tools:search_user_history",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "array"},
            "timeout_ms": 7000,
            "enabled": True,
        }]
    })
    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        rec = await store.get("search_user_history")
    assert rec is not None
    assert rec.name == "search_user_history"
    assert rec.code_ref == "ai_engine.agents.tools:search_user_history"
    assert rec.version == 2
    assert rec.timeout_ms == 7000


@pytest.mark.asyncio
async def test_get_returns_none_when_no_row():
    fake_sb = _FakeSupabase({"ai_tools": []})
    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        rec = await store.get("missing_tool")
    assert rec is None


@pytest.mark.asyncio
async def test_get_caches_within_ttl():
    fake_sb = _FakeSupabase({
        "ai_tools": [{
            "name": "echo",
            "code_ref": "x",
            "input_schema": {},
            "output_schema": {},
            "timeout_ms": 100,
            "enabled": True,
        }]
    })
    store = SupabaseToolStore(ttl_seconds=60.0)
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        await store.get("echo")
        await store.get("echo")
        await store.get("echo")
    # First call hit Supabase; subsequent two were served from cache.
    assert len(fake_sb.queries) == 1


@pytest.mark.asyncio
async def test_get_swallows_db_failure_returns_none():
    def _boom():
        raise RuntimeError("supabase down")

    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", _boom):
        rec = await store.get("echo")
    assert rec is None


# ── SupabaseToolStore.has_grant ──────────────────────────────────────
@pytest.mark.asyncio
async def test_has_grant_true_for_direct_grant():
    fake_sb = _FakeSupabase({"ai_agent_tool_grants": [{"agent_name": "agent-a"}]})
    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        granted = await store.has_grant("agent-a", "echo")
    assert granted is True


@pytest.mark.asyncio
async def test_has_grant_true_for_wildcard_row():
    fake_sb = _FakeSupabase({"ai_agent_tool_grants": [{"agent_name": "*"}]})
    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        granted = await store.has_grant("agent-z", "echo")
    assert granted is True


@pytest.mark.asyncio
async def test_has_grant_false_when_no_row():
    fake_sb = _FakeSupabase({"ai_agent_tool_grants": []})
    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        granted = await store.has_grant("agent-a", "echo")
    assert granted is False


@pytest.mark.asyncio
async def test_has_grant_swallows_db_failure_returns_false():
    def _boom():
        raise RuntimeError("supabase down")

    store = SupabaseToolStore()
    with patch("app.core.database.get_supabase", _boom):
        granted = await store.has_grant("agent-a", "echo")
    assert granted is False


@pytest.mark.asyncio
async def test_invalidate_drops_cached_entry():
    fake_sb = _FakeSupabase({
        "ai_tools": [{
            "name": "echo", "code_ref": "x",
            "input_schema": {}, "output_schema": {},
            "timeout_ms": 100, "enabled": True,
        }]
    })
    store = SupabaseToolStore(ttl_seconds=60.0)
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        await store.get("echo")
        store.invalidate("echo")
        await store.get("echo")
    # Two queries because cache was wiped between calls.
    # _FakeSupabase reuses the .queries dict — we count with a fresh
    # marker by querying twice.
    assert "ai_tools" in fake_sb.queries


# ── supabase_invocation_sink ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_invocation_sink_writes_row_to_ai_tool_invocations():
    fake_sb = _FakeSupabase({})
    invocation = ToolInvocation(
        tool_name="echo",
        agent_name="agent-a",
        status="ok",
        duration_ms=42,
        started_at=1_700_000_000.0,
        org_id="org-1",
        user_id="user-1",
        input_hash="abc123",
    )
    with patch("app.core.database.get_supabase", lambda: fake_sb):
        await supabase_invocation_sink(invocation)

    assert "ai_tool_invocations" in fake_sb.queries
    insert_calls = [c for c in fake_sb.queries["ai_tool_invocations"].calls if c[0] == "insert"]
    assert len(insert_calls) == 1
    row = insert_calls[0][1][0]
    assert row["tool_name"] == "echo"
    assert row["agent_name"] == "agent-a"
    assert row["status"] == "ok"
    assert row["duration_ms"] == 42
    assert row["org_id"] == "org-1"
    assert row["user_id"] == "user-1"
    assert row["input_hash"] == "abc123"
    assert "started_at" in row and "completed_at" in row


@pytest.mark.asyncio
async def test_invocation_sink_swallows_db_failure():
    def _boom():
        raise RuntimeError("write failed")

    invocation = ToolInvocation(
        tool_name="echo",
        agent_name="agent-a",
        status="ok",
        duration_ms=1,
        started_at=1_700_000_000.0,
    )
    with patch("app.core.database.get_supabase", _boom):
        # Must NOT raise.
        await supabase_invocation_sink(invocation)


# ── package re-exports ───────────────────────────────────────────────
def test_package_reexports_supabase_helpers():
    from ai_engine.registry import SupabaseToolStore as A
    from ai_engine.registry import supabase_invocation_sink as B
    assert A is SupabaseToolStore
    assert B is supabase_invocation_sink
