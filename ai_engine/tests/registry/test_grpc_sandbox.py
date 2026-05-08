"""Tests for the L2 gRPC sandbox runtime (m11-pr44)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

from ai_engine.registry import grpc_sandbox as gs
from ai_engine.registry.resolvers import UnknownCodeRef
from ai_engine.registry.sandboxes import (
    L2GrpcSidecarSandbox,
    SandboxNotImplemented,
)
from ai_engine.registry.tools import ToolRecord


# ── codec round-trip ───────────────────────────────────────────────────


def test_request_codec_round_trip() -> None:
    raw = gs._encode_request("pkg.mod:fn", {"x": 1, "y": "two"})
    code_ref, args = gs._decode_request(raw)
    assert code_ref == "pkg.mod:fn"
    assert args == {"x": 1, "y": "two"}


def test_response_ok_codec_round_trip() -> None:
    raw = gs._encode_response_ok({"result": [1, 2, 3]})
    assert gs._decode_response(raw) == {"result": [1, 2, 3]}


def test_response_err_decodes_to_remote_error() -> None:
    raw = gs._encode_response_err("BoomError", "oops")
    with pytest.raises(gs.L2RemoteError) as ei:
        gs._decode_response(raw)
    assert ei.value.kind == "BoomError"
    assert ei.value.message == "oops"


def test_request_too_large_rejected() -> None:
    big = {"x": "z" * (gs.MAX_REQUEST_BYTES + 10)}
    with pytest.raises(ValueError, match="exceeds limit"):
        gs._encode_request("ref", big)


def test_decode_request_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        gs._decode_request(b'"not an object"')


def test_decode_request_rejects_missing_fields() -> None:
    with pytest.raises(ValueError):
        gs._decode_request(b'{"code_ref": ""}')
    with pytest.raises(ValueError):
        gs._decode_request(b'{"code_ref": "x"}')  # missing arguments


# ── L2 sandbox flag-OFF preserves SandboxNotImplemented contract ──────


@pytest.mark.asyncio
async def test_l2_disabled_raises_sandbox_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FF_TOOL_L2_GRPC_ENABLED", raising=False)
    rec = ToolRecord(name="search_user_history", code_ref="pkg.mod:fn", sandbox_tier="L2")

    async def fn(**_: Any) -> Any:
        return None

    with pytest.raises(SandboxNotImplemented, match=rec.name):
        await L2GrpcSidecarSandbox().invoke(fn, arguments={}, record=rec)


# ── server invoke handler exercised directly ──────────────────────────


@pytest.mark.asyncio
async def test_invoke_handler_resolves_and_calls_fn() -> None:
    seen: dict[str, Any] = {}

    async def fake_tool(**kw: Any) -> dict:
        seen.update(kw)
        return {"echo": kw}

    def resolver(code_ref: str):
        assert code_ref == "fake:tool"
        return fake_tool

    raw_req = gs._encode_request("fake:tool", {"a": 1, "b": "two"})
    raw_resp = await gs._invoke_handler(raw_req, context=None, resolver=resolver)  # type: ignore[arg-type]
    assert gs._decode_response(raw_resp) == {"echo": {"a": 1, "b": "two"}}
    assert seen == {"a": 1, "b": "two"}


@pytest.mark.asyncio
async def test_invoke_handler_unknown_code_ref() -> None:
    def resolver(code_ref: str):
        raise UnknownCodeRef(f"no such ref: {code_ref}")

    raw_req = gs._encode_request("missing:fn", {})
    raw_resp = await gs._invoke_handler(raw_req, context=None, resolver=resolver)  # type: ignore[arg-type]
    obj = json.loads(raw_resp)
    assert obj["ok"] is False
    assert obj["error_kind"] == "UnknownCodeRef"


@pytest.mark.asyncio
async def test_invoke_handler_runtime_exception_returns_error_envelope() -> None:
    async def boom(**_: Any) -> Any:
        raise ValueError("nope")

    def resolver(code_ref: str):
        return boom

    raw_resp = await gs._invoke_handler(
        gs._encode_request("x:y", {}), context=None, resolver=resolver  # type: ignore[arg-type]
    )
    obj = json.loads(raw_resp)
    assert obj == {"ok": False, "error_kind": "ValueError", "error_message": "nope"}


@pytest.mark.asyncio
async def test_invoke_handler_bad_json_returns_bad_request() -> None:
    raw_resp = await gs._invoke_handler(b"not json", context=None)  # type: ignore[arg-type]
    obj = json.loads(raw_resp)
    assert obj["ok"] is False
    assert obj["error_kind"] == "BadRequest"


# ── full client/server round-trip over real grpc.aio ──────────────────


@pytest.mark.asyncio
async def test_inproc_client_server_round_trip() -> None:
    """Spin up an inproc server, call it through the gRPC channel."""
    call_log: list[dict[str, Any]] = []

    async def echo_tool(**kw: Any) -> dict:
        call_log.append(kw)
        return {"got": kw}

    def resolver(code_ref: str):
        assert code_ref == "test:echo"
        return echo_tool

    handle = await gs.start_inproc_server(resolver=resolver)
    try:
        client = gs._Client(handle.target)
        try:
            out = await client.invoke(
                code_ref="test:echo",
                arguments={"k": "v"},
                timeout_s=5.0,
            )
            assert out == {"got": {"k": "v"}}
            assert call_log == [{"k": "v"}]
        finally:
            await client.close()
    finally:
        await handle.server.stop(0.5)


@pytest.mark.asyncio
async def test_inproc_round_trip_propagates_remote_error() -> None:
    async def boom(**_: Any) -> Any:
        raise KeyError("missing")

    def resolver(code_ref: str):
        return boom

    handle = await gs.start_inproc_server(resolver=resolver)
    try:
        client = gs._Client(handle.target)
        try:
            with pytest.raises(gs.L2RemoteError) as ei:
                await client.invoke(
                    code_ref="x:y", arguments={}, timeout_s=5.0
                )
            assert ei.value.kind == "KeyError"
        finally:
            await client.close()
    finally:
        await handle.server.stop(0.5)


# ── L2 sandbox flag-ON delegates to runtime ──────────────────────────


@pytest.mark.asyncio
async def test_l2_enabled_routes_through_grpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the flag on, L2GrpcSidecarSandbox spins up the runtime
    and round-trips a real call through gRPC."""
    # Reset singleton so the test is hermetic.
    await gs.shutdown_runtime(grace=0.1)

    async def adder(**kw: Any) -> int:
        return int(kw["a"]) + int(kw["b"])

    # Patch the resolver path so we don't need a real RESOLVERS entry.
    monkeypatch.setattr(gs, "resolve", lambda code_ref: adder)
    monkeypatch.setenv("FF_TOOL_L2_GRPC_ENABLED", "1")
    monkeypatch.setenv("FF_TOOL_L2_GRPC_TARGET", "inproc")

    rec = ToolRecord(
        name="adder",
        code_ref="test:adder",
        sandbox_tier="L2",
        timeout_ms=5_000,
    )

    async def unused(**_: Any) -> Any:  # signature parity with sandbox protocol
        raise AssertionError("L2 must call through the sidecar, not fn")

    try:
        result = await L2GrpcSidecarSandbox().invoke(
            unused, arguments={"a": 2, "b": 3}, record=rec
        )
        assert result == 5
    finally:
        await gs.shutdown_runtime(grace=0.1)
