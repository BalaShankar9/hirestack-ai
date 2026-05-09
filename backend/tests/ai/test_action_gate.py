"""Action-gate contract pin (m12-pr17).

The "action gate" per blueprint §6.2 is `Dispatcher.invoke`: the single
choke-point that decides whether a model-proposed tool call may execute.

Rich mechanism tests already live next to the dispatcher in
`ai_engine/tests/registry/test_dispatcher.py` (grant flow, capability
tokens, sandbox routing, schema validation). This file pins the
**cross-cutting contract invariants** that hold across every code path:

1. Status enum is closed (no surprise statuses leak into ai_tool_invocations).
2. Audit row count = 1 per invoke, regardless of branch (no double-write,
   no silent skip).
3. Resolver is never called when the gate denies (grant, capability,
   invalid input). Side-effect-freedom on the deny path is the whole
   point of the gate.
4. duration_ms is non-negative on every audit row.
5. error_message is truncated to 500 chars (DB column / UI invariant).
6. input_hash is deterministic across invocations with identical args.
7. org_id / user_id propagate to the audit row on every status.
8. Sink failure never masks the tool result (audit best-effort).

If any of these break, the action-gate boundary stops being a
boundary — model-proposed actions could leak side effects, or the
audit log could lose the evidence that they were blocked.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

# The dispatcher lives in ai_engine/, which is a sibling of backend/.
# Tests under backend/ run with backend/ on sys.path; add the repo root
# so `ai_engine` is importable.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_engine.registry import (  # noqa: E402
    Authorizer,
    CapabilityRequired,
    Dispatcher,
    GrantDenied,
    InProcessNonceStore,
    InvalidInput,
    InvalidOutput,
    ToolInvocation,
    ToolNotFound,
    ToolTimeout,
)
from ai_engine.registry.tools import InMemoryToolStore, ToolRecord  # noqa: E402

# Closed set of statuses the gate may emit. If a new status is added
# downstream consumers (Grafana panels, the ai_tool_invocations RLS
# query, the cost-aggregation cron) must be updated. This test catches
# silent additions.
ALLOWED_STATUSES: frozenset[str] = frozenset(
    {"ok", "denied", "invalid_input", "invalid_output", "timeout", "error"}
)
# Hard column cap for ai_tool_invocations.error_message.
ERROR_MESSAGE_MAX_CHARS = 500


# ── helpers (intentionally local, don't share with the dispatcher's
#     own test fixtures so this file remains independent) -----------------


def _record(*, requires_token: bool = False) -> ToolRecord:
    return ToolRecord(
        name="echo",
        code_ref="tests.echo",
        input_schema={
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
        output_schema={"type": "object"},
        timeout_ms=5_000,
        requires_capability_token=requires_token,
    )


def _store(*, granted: bool = True, requires_token: bool = False) -> InMemoryToolStore:
    grants: set[tuple[str, str]] = set()
    if granted:
        grants.add(("agent-a", "echo"))
    return InMemoryToolStore(
        tools={"echo": _record(requires_token=requires_token)}, grants=grants
    )


def _make_gate(
    store: InMemoryToolStore,
    fn,
    *,
    sink=None,
    authorizer: Authorizer | None = None,
) -> Dispatcher:
    return Dispatcher(
        store=store,
        resolver=lambda _ref: fn,
        sink=sink,
        authorizer=authorizer,
        _enabled_override=True,
    )


class _CallCounter:
    """Resolver wrapper that records whether it was actually invoked."""

    def __init__(self, return_value: Any | None = None, raise_exc: Exception | None = None) -> None:
        self.calls = 0
        self._ret = return_value if return_value is not None else {"ok": True}
        self._exc = raise_exc

    async def __call__(self, **kwargs: Any) -> Any:  # noqa: D401
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._ret


# ── (1) status enum is closed --------------------------------------------


@pytest.mark.asyncio
async def test_status_enum_remains_closed_across_every_branch() -> None:
    """Drive every branch the gate can emit; assert each status is in
    the closed allowlist."""
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    # ok
    fn_ok = _CallCounter(return_value={"echoed": "x"})
    g = _make_gate(_store(), fn_ok, sink=sink)
    await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    # denied (grant)
    g = _make_gate(_store(granted=False), _CallCounter(), sink=sink)
    with pytest.raises(GrantDenied):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    # invalid_input
    g = _make_gate(_store(), _CallCounter(), sink=sink)
    with pytest.raises(InvalidInput):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={})

    # invalid_output
    g = _make_gate(_store(), _CallCounter(return_value="not-an-object"), sink=sink)
    with pytest.raises(InvalidOutput):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    # timeout
    async def slow(**_: Any) -> dict:
        await asyncio.sleep(1.0)
        return {}

    rec = _record()
    rec.timeout_ms = 5
    store_slow = InMemoryToolStore(tools={"echo": rec}, grants={("agent-a", "echo")})
    g = _make_gate(store_slow, slow, sink=sink)
    with pytest.raises(ToolTimeout):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    # error
    g = _make_gate(_store(), _CallCounter(raise_exc=RuntimeError("boom")), sink=sink)
    with pytest.raises(RuntimeError):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    seen_statuses = {inv.status for inv in audited}
    assert seen_statuses <= ALLOWED_STATUSES, (
        f"unknown status escaped audit: {seen_statuses - ALLOWED_STATUSES}"
    )
    # We exercised every allowed status except possibly invalid_output's
    # parent — sanity check that we covered most of the enum.
    assert {"ok", "denied", "invalid_input", "invalid_output", "timeout", "error"} <= seen_statuses


# ── (2) audit row count = 1 per invoke, every branch ---------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["ok", "denied", "invalid_input", "invalid_output", "timeout", "error"],
)
async def test_exactly_one_audit_row_per_invoke(scenario: str) -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    if scenario == "ok":
        g = _make_gate(_store(), _CallCounter(return_value={"x": 1}), sink=sink)
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    elif scenario == "denied":
        g = _make_gate(_store(granted=False), _CallCounter(), sink=sink)
        with pytest.raises(GrantDenied):
            await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    elif scenario == "invalid_input":
        g = _make_gate(_store(), _CallCounter(), sink=sink)
        with pytest.raises(InvalidInput):
            await g.invoke(tool_name="echo", agent_name="agent-a", arguments={})
    elif scenario == "invalid_output":
        g = _make_gate(_store(), _CallCounter(return_value="bad"), sink=sink)
        with pytest.raises(InvalidOutput):
            await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    elif scenario == "timeout":
        rec = _record()
        rec.timeout_ms = 5

        async def slow(**_: Any) -> dict:
            await asyncio.sleep(1.0)
            return {}

        st = InMemoryToolStore(tools={"echo": rec}, grants={("agent-a", "echo")})
        g = _make_gate(st, slow, sink=sink)
        with pytest.raises(ToolTimeout):
            await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    elif scenario == "error":
        g = _make_gate(_store(), _CallCounter(raise_exc=RuntimeError("boom")), sink=sink)
        with pytest.raises(RuntimeError):
            await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    assert len(audited) == 1, f"{scenario}: expected 1 audit row, got {len(audited)}"


# ── (3) resolver is never called on a deny --------------------------------


@pytest.mark.asyncio
async def test_resolver_not_called_on_grant_deny() -> None:
    counter = _CallCounter()
    g = _make_gate(_store(granted=False), counter)
    with pytest.raises(GrantDenied):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    assert counter.calls == 0, "resolver ran despite gate-deny — side effects possible"


@pytest.mark.asyncio
async def test_resolver_not_called_on_invalid_input() -> None:
    counter = _CallCounter()
    g = _make_gate(_store(), counter)
    with pytest.raises(InvalidInput):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={})
    assert counter.calls == 0


@pytest.mark.asyncio
async def test_resolver_not_called_when_capability_token_missing() -> None:
    counter = _CallCounter()
    auth = Authorizer(secret=b"test-secret-32bytes-min-len!!!", nonce_store=InProcessNonceStore())
    g = _make_gate(_store(requires_token=True), counter, authorizer=auth)
    with pytest.raises(CapabilityRequired):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    assert counter.calls == 0


@pytest.mark.asyncio
async def test_resolver_not_called_when_unknown_tool() -> None:
    counter = _CallCounter()
    g = _make_gate(_store(), counter)
    with pytest.raises(ToolNotFound):
        await g.invoke(tool_name="nope", agent_name="agent-a", arguments={"text": "x"})
    assert counter.calls == 0


# ── (4) duration_ms is non-negative ---------------------------------------


@pytest.mark.asyncio
async def test_duration_ms_is_non_negative_on_every_audit_row() -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    # ok
    g = _make_gate(_store(), _CallCounter(return_value={"x": 1}), sink=sink)
    await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    # error
    g = _make_gate(_store(), _CallCounter(raise_exc=RuntimeError("e")), sink=sink)
    with pytest.raises(RuntimeError):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    for inv in audited:
        assert inv.duration_ms >= 0, f"negative duration: {inv}"


# ── (5) error_message truncated to 500 chars ------------------------------


@pytest.mark.asyncio
async def test_error_message_truncated_to_500_chars() -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    huge = "x" * 5_000
    g = _make_gate(_store(), _CallCounter(raise_exc=RuntimeError(huge)), sink=sink)
    with pytest.raises(RuntimeError):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})

    assert len(audited) == 1
    msg = audited[0].error_message or ""
    assert len(msg) <= ERROR_MESSAGE_MAX_CHARS, (
        f"error_message length {len(msg)} > {ERROR_MESSAGE_MAX_CHARS} — "
        "DB column cap will silently truncate or insert will fail"
    )
    assert msg == "x" * ERROR_MESSAGE_MAX_CHARS


# ── (6) input_hash is deterministic ---------------------------------------


@pytest.mark.asyncio
async def test_input_hash_is_stable_across_identical_invocations() -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    g = _make_gate(_store(), _CallCounter(return_value={"x": 1}), sink=sink)

    await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "abc"})
    await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "abc"})
    await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "different"})

    assert len(audited) == 3
    h1, h2, h3 = (a.input_hash for a in audited)
    assert h1 == h2, "identical args produced different hashes — caching is broken"
    assert h1 != h3, "different args produced identical hashes — collision risk"
    # The current implementation truncates to 32 hex chars.
    for h in (h1, h2, h3):
        assert h is not None and len(h) == 32 and all(c in "0123456789abcdef" for c in h)


@pytest.mark.asyncio
async def test_input_hash_independent_of_key_order() -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    rec = _record()
    rec.input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {"text": {"type": "string"}, "tag": {"type": "string"}},
    }
    st = InMemoryToolStore(tools={"echo": rec}, grants={("agent-a", "echo")})
    g = _make_gate(st, _CallCounter(return_value={"x": 1}), sink=sink)

    await g.invoke(
        tool_name="echo",
        agent_name="agent-a",
        arguments={"text": "x", "tag": "y"},
    )
    await g.invoke(
        tool_name="echo",
        agent_name="agent-a",
        arguments={"tag": "y", "text": "x"},
    )
    assert audited[0].input_hash == audited[1].input_hash, (
        "hash is order-dependent — same args produce different audit fingerprints"
    )


# ── (7) org_id / user_id propagate to every audit row --------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["ok", "denied", "invalid_input", "error"],
)
async def test_org_and_user_id_propagate_to_audit_row(scenario: str) -> None:
    audited: list[ToolInvocation] = []

    async def sink(inv: ToolInvocation) -> None:
        audited.append(inv)

    if scenario == "ok":
        g = _make_gate(_store(), _CallCounter(return_value={"x": 1}), sink=sink)
        await g.invoke(
            tool_name="echo",
            agent_name="agent-a",
            arguments={"text": "x"},
            org_id="org-42",
            user_id="user-7",
        )
    elif scenario == "denied":
        g = _make_gate(_store(granted=False), _CallCounter(), sink=sink)
        with pytest.raises(GrantDenied):
            await g.invoke(
                tool_name="echo",
                agent_name="agent-a",
                arguments={"text": "x"},
                org_id="org-42",
                user_id="user-7",
            )
    elif scenario == "invalid_input":
        g = _make_gate(_store(), _CallCounter(), sink=sink)
        with pytest.raises(InvalidInput):
            await g.invoke(
                tool_name="echo",
                agent_name="agent-a",
                arguments={},
                org_id="org-42",
                user_id="user-7",
            )
    elif scenario == "error":
        g = _make_gate(_store(), _CallCounter(raise_exc=RuntimeError("boom")), sink=sink)
        with pytest.raises(RuntimeError):
            await g.invoke(
                tool_name="echo",
                agent_name="agent-a",
                arguments={"text": "x"},
                org_id="org-42",
                user_id="user-7",
            )

    assert len(audited) == 1
    assert audited[0].org_id == "org-42", f"{scenario}: org_id lost"
    assert audited[0].user_id == "user-7", f"{scenario}: user_id lost"


# ── (8) sink failure never masks the tool ---------------------------------


@pytest.mark.asyncio
async def test_sink_exception_does_not_mask_successful_invocation() -> None:
    """An audit-write failure must NEVER take down a tool call. The
    gate is best-effort about audit because the alternative — failing
    the user's request because Postgres is slow — is worse."""

    async def broken_sink(_: ToolInvocation) -> None:
        raise RuntimeError("sink down")

    g = _make_gate(_store(), _CallCounter(return_value={"echoed": "x"}), sink=broken_sink)
    out = await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
    assert out == {"echoed": "x"}


@pytest.mark.asyncio
async def test_sink_exception_does_not_mask_original_tool_error() -> None:
    """If the tool raises AND the sink raises, the tool error must
    still be the one surfaced — operators can rely on the exception
    type to drive incident response."""

    async def broken_sink(_: ToolInvocation) -> None:
        raise RuntimeError("sink down")

    g = _make_gate(_store(), _CallCounter(raise_exc=ValueError("real error")), sink=broken_sink)
    with pytest.raises(ValueError, match="real error"):
        await g.invoke(tool_name="echo", agent_name="agent-a", arguments={"text": "x"})
