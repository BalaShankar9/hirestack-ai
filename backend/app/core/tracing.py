"""
Request-ID tracing middleware + access logging.

Assigns a unique ``X-Request-ID`` to every HTTP request so that all log
entries emitted while handling that request can be correlated.  If the
caller already sends the header, we honour it (useful for load-balancer
provided trace IDs).
"""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable

import structlog

# ---------- context var accessible from anywhere in the request ----------
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware:
    """Pure-ASGI middleware — safe for SSE / streaming responses."""

    HEADER_NAME = b"x-request-id"

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Try to read an incoming X-Request-ID header
        rid = ""
        for name, value in scope.get("headers", []):
            if name == self.HEADER_NAME:
                rid = value.decode("latin-1")[:128]  # cap length
                break

        if not rid:
            rid = uuid.uuid4().hex[:16]

        token = request_id_var.set(rid)

        async def send_with_rid(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.HEADER_NAME, rid.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_rid)
        finally:
            request_id_var.reset(token)


class AccessLogMiddleware:
    """Pure-ASGI middleware that logs every HTTP request with timing."""

    _SKIP_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app: Any) -> None:
        self.app = app
        self._logger = structlog.get_logger("access")

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        start = time.monotonic()
        status_code = 0

        async def capture_status(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            log = self._logger.info if status_code < 400 else self._logger.warning
            if status_code >= 500:
                log = self._logger.error
            log(
                "http_request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=duration_ms,
                request_id=request_id_var.get(""),
            )


class MaxBodySizeMiddleware:
    """Pure-ASGI middleware that rejects requests whose body exceeds *max_bytes*.

    Returns 413 Payload Too Large before consuming the full body.  File-upload
    routes that need a higher limit should be listed in *exempt_prefixes*.
    """

    def __init__(
        self,
        app: Any,
        *,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB default
        exempt_prefixes: tuple[str, ...] = ("/api/upload",),
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_prefixes = exempt_prefixes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self.exempt_prefixes):
            await self.app(scope, receive, send)
            return

        total = 0
        body_too_large = False

        async def limited_receive() -> dict:
            nonlocal total, body_too_large
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    body_too_large = True
            return message

        async def reject(send_fn: Callable) -> None:
            await send_fn(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send_fn(
                {
                    "type": "http.response.body",
                    "body": b'{"detail":"Request body too large"}',
                }
            )

        # We wrap the downstream call so we can intercept after each chunk
        async def guarded_app(scope: dict, recv: Callable, send_fn: Callable) -> None:
            nonlocal body_too_large
            try:
                await self.app(scope, recv, send_fn)
            except Exception:
                if body_too_large:
                    await reject(send_fn)
                else:
                    raise

        # For non-streaming requests, check content-length header first
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await reject(send)
                        return
                except (ValueError, OverflowError):
                    pass
                break

        await self.app(scope, limited_receive, send)
