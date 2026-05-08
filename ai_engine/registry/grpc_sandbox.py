"""L2 gRPC sandbox runtime (M11-pr44).

Minimal in-process gRPC sandbox for the L2 tier. Runs in the same
Python process as the dispatcher by default; can be detached into
its own ``tool-runner`` sidecar later by pointing
``FF_TOOL_L2_GRPC_TARGET`` at a remote ``host:port``.

Wire format
-----------
Single unary-unary RPC: ``/hirestack.L2Sandbox/Invoke``.

* Request bytes: UTF-8 JSON ``{"code_ref": "...", "arguments": {...}}``.
* Response bytes: UTF-8 JSON ``{"ok": true, "result": <jsonable>}`` on
  success, ``{"ok": false, "error_kind": "...", "error_message": "..."}``
  on failure (including ``UnknownCodeRef`` and runtime exceptions).

Why no ``.proto`` here
----------------------
A generated stub buys us message validation and forward-compat, but
also drags ``grpcio-tools`` / ``protoc`` into the build, plus a
generated module that has to be checked in. The current contract is
JSON-in / JSON-out — that's small enough that hand-rolling the
``RpcMethodHandler`` keeps the dependency surface tiny while still
letting us route through real gRPC transport (with all its retry,
deadline, and cancellation semantics).

Feature flagging
----------------
* ``FF_TOOL_SANDBOX_TIER_ROUTING`` (existing, default OFF) — controls
  whether ``select_sandbox`` returns L2 at all.
* ``FF_TOOL_L2_GRPC_ENABLED`` (new, default OFF) — controls whether
  the L2 sandbox actually attempts the RPC. With this OFF, calling
  L2 still raises ``SandboxNotImplemented`` (legacy behaviour).
* ``FF_TOOL_L2_GRPC_TARGET`` (new, default ``inproc``) — either the
  literal ``inproc`` (start an in-process server on first invoke
  and keep it running) or a ``host:port`` string for an external
  sidecar.

Both flags are OFF by default → m7-pr29 contract is preserved
verbatim.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import grpc
import grpc.aio

from .resolvers import UnknownCodeRef, resolve
from .sandboxes import SandboxNotImplemented
from .tools import ToolRecord

logger = logging.getLogger(__name__)


# ── wire constants ─────────────────────────────────────────────────────

GRPC_SERVICE = "hirestack.L2Sandbox"
GRPC_METHOD = "Invoke"
GRPC_FULL_METHOD = f"/{GRPC_SERVICE}/{GRPC_METHOD}"

# JSON payload limits — generous but bounded so a misbehaving caller
# can't OOM the runner.
MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # 4 MiB


# ── codec ──────────────────────────────────────────────────────────────


def _encode_request(code_ref: str, arguments: dict[str, Any]) -> bytes:
    payload = json.dumps(
        {"code_ref": code_ref, "arguments": arguments},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError(
            f"L2 request {len(payload)}B exceeds limit {MAX_REQUEST_BYTES}B"
        )
    return payload


def _decode_request(raw: bytes) -> tuple[str, dict[str, Any]]:
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("L2 request payload must be a JSON object")
    code_ref = obj.get("code_ref")
    arguments = obj.get("arguments")
    if not isinstance(code_ref, str) or not code_ref:
        raise ValueError("L2 request missing string field 'code_ref'")
    if not isinstance(arguments, dict):
        raise ValueError("L2 request missing object field 'arguments'")
    return code_ref, arguments


def _encode_response_ok(result: Any) -> bytes:
    payload = json.dumps(
        {"ok": True, "result": result},
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,  # tolerate non-JSON tool returns at the boundary
    ).encode("utf-8")
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError(
            f"L2 response {len(payload)}B exceeds limit {MAX_RESPONSE_BYTES}B"
        )
    return payload


def _encode_response_err(kind: str, message: str) -> bytes:
    return json.dumps(
        {"ok": False, "error_kind": kind, "error_message": message},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _decode_response(raw: bytes) -> Any:
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("L2 response must be a JSON object")
    if obj.get("ok") is True:
        return obj.get("result")
    raise L2RemoteError(
        kind=str(obj.get("error_kind", "Unknown")),
        message=str(obj.get("error_message", "")),
    )


# ── exceptions ─────────────────────────────────────────────────────────


class L2RemoteError(RuntimeError):
    """Server-side error reported back via the JSON envelope."""

    def __init__(self, *, kind: str, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


# ── server ─────────────────────────────────────────────────────────────


async def _invoke_handler(
    request_bytes: bytes,
    context: grpc.aio.ServicerContext,
    *,
    resolver: Optional[Callable[[str], Callable[..., Awaitable[Any]]]] = None,
) -> bytes:
    """Server-side RPC handler. Resolves code_ref + invokes the tool."""
    # Late-bind the resolver so monkeypatching ``grpc_sandbox.resolve``
    # (or the underlying RESOLVERS map) takes effect at call time.
    if resolver is None:
        resolver = resolve
    try:
        code_ref, arguments = _decode_request(request_bytes)
    except (ValueError, json.JSONDecodeError) as exc:
        return _encode_response_err("BadRequest", str(exc))

    try:
        fn = resolver(code_ref)
    except UnknownCodeRef as exc:
        return _encode_response_err("UnknownCodeRef", str(exc))

    try:
        result = await fn(**arguments)
    except Exception as exc:  # noqa: BLE001 — boundary catch is the point
        return _encode_response_err(type(exc).__name__, str(exc))

    try:
        return _encode_response_ok(result)
    except (TypeError, ValueError) as exc:
        return _encode_response_err("EncodingError", str(exc))


def _make_generic_handler(
    *,
    resolver: Optional[Callable[[str], Callable[..., Awaitable[Any]]]] = None,
) -> grpc.GenericRpcHandler:
    """Builds a grpc.GenericRpcHandler that serves the Invoke method."""

    async def _wrapper(
        request_bytes: bytes, context: grpc.aio.ServicerContext
    ) -> bytes:
        # Pass resolver=None when the caller didn't override; the
        # handler will late-bind to the current ``resolve`` symbol.
        return await _invoke_handler(request_bytes, context, resolver=resolver)

    method_handler = grpc.unary_unary_rpc_method_handler(
        _wrapper,
        request_deserializer=lambda b: b,
        response_serializer=lambda b: b,
    )

    class _Handler(grpc.GenericRpcHandler):
        def service(self, handler_call_details):  # type: ignore[override]
            if handler_call_details.method == GRPC_FULL_METHOD:
                return method_handler
            return None

    return _Handler()


@dataclass
class _ServerHandle:
    server: grpc.aio.Server
    target: str  # "host:port"


async def start_inproc_server(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    resolver: Optional[Callable[[str], Callable[..., Awaitable[Any]]]] = None,
) -> _ServerHandle:
    """Start an in-process gRPC server bound to localhost.

    ``port=0`` lets the OS pick an ephemeral port — the actual port
    is read back from the bound socket and returned in the handle.
    """
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((_make_generic_handler(resolver=resolver),))
    bound_port = server.add_insecure_port(f"{host}:{port}")
    await server.start()
    return _ServerHandle(server=server, target=f"{host}:{bound_port}")


# ── client ─────────────────────────────────────────────────────────────


class _Client:
    """Thin async client around the unary Invoke RPC."""

    def __init__(self, target: str) -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None
        self._lock = asyncio.Lock()

    async def _ensure_channel(self) -> grpc.aio.Channel:
        if self._channel is None:
            async with self._lock:
                if self._channel is None:
                    self._channel = grpc.aio.insecure_channel(self._target)
        return self._channel

    async def invoke(
        self,
        *,
        code_ref: str,
        arguments: dict[str, Any],
        timeout_s: float,
    ) -> Any:
        channel = await self._ensure_channel()
        call = channel.unary_unary(
            GRPC_FULL_METHOD,
            request_serializer=lambda b: b,
            response_deserializer=lambda b: b,
        )
        request_bytes = _encode_request(code_ref, arguments)
        response_bytes: bytes = await call(request_bytes, timeout=timeout_s)
        return _decode_response(response_bytes)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None


# ── runtime singleton ──────────────────────────────────────────────────

_singleton_lock = threading.Lock()
_singleton: dict[str, Any] = {"server": None, "client": None, "target": None}


async def _ensure_runtime() -> _Client:
    """Return the active L2 client. Lazy-starts the in-process server.

    ``FF_TOOL_L2_GRPC_TARGET`` controls behaviour:
    * ``"inproc"`` (default) — start an in-process server once and reuse.
    * ``"host:port"`` — use the external sidecar; no server is started.
    """
    target_env = os.getenv("FF_TOOL_L2_GRPC_TARGET", "inproc").strip()
    with _singleton_lock:
        cached_client = _singleton["client"]
        cached_target = _singleton["target"]
    if cached_client is not None and cached_target == target_env:
        return cached_client  # type: ignore[return-value]

    if target_env == "" or target_env.lower() == "inproc":
        handle = await start_inproc_server()
        client = _Client(handle.target)
        with _singleton_lock:
            _singleton["server"] = handle.server
            _singleton["client"] = client
            _singleton["target"] = target_env
        logger.info(
            "tool_sandbox_l2_inproc_started",
            extra={"target": handle.target},
        )
        return client

    client = _Client(target_env)
    with _singleton_lock:
        _singleton["server"] = None
        _singleton["client"] = client
        _singleton["target"] = target_env
    logger.info(
        "tool_sandbox_l2_external_target",
        extra={"target": target_env},
    )
    return client


async def shutdown_runtime(*, grace: float = 1.0) -> None:
    """Tear down the runtime — used by tests and clean shutdown paths."""
    with _singleton_lock:
        server = _singleton["server"]
        client = _singleton["client"]
        _singleton["server"] = None
        _singleton["client"] = None
        _singleton["target"] = None
    if client is not None:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 — best-effort
            pass
    if server is not None:
        try:
            await server.stop(grace)
        except Exception:  # noqa: BLE001 — best-effort
            pass


def is_grpc_enabled() -> bool:
    """``FF_TOOL_L2_GRPC_ENABLED`` gate. Default OFF."""
    return os.getenv("FF_TOOL_L2_GRPC_ENABLED", "0").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ── sandbox class wired into the dispatcher ────────────────────────────


class L2GrpcSandboxRuntime:
    """Real L2 sandbox. Routes the call through the gRPC sidecar.

    Falls back to ``SandboxNotImplemented`` when the L2 grpc flag is
    OFF — preserves the m7-pr29 default behaviour.
    """

    async def invoke(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        arguments: dict[str, Any],
        record: ToolRecord,
    ) -> Any:
        if not is_grpc_enabled():
            raise SandboxNotImplemented(
                f"L2 tool-runner sidecar disabled "
                f"(set FF_TOOL_L2_GRPC_ENABLED=1; tool={record.name})."
            )
        client = await _ensure_runtime()
        timeout_s = max(0.001, record.timeout_ms / 1000.0)
        return await client.invoke(
            code_ref=record.code_ref,
            arguments=arguments,
            timeout_s=timeout_s,
        )


__all__ = [
    "GRPC_FULL_METHOD",
    "GRPC_METHOD",
    "GRPC_SERVICE",
    "L2GrpcSandboxRuntime",
    "L2RemoteError",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "is_grpc_enabled",
    "shutdown_runtime",
    "start_inproc_server",
]
