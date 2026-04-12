"""
Request-ID tracing middleware.

Assigns a unique ``X-Request-ID`` to every HTTP request so that all log
entries emitted while handling that request can be correlated.  If the
caller already sends the header, we honour it (useful for load-balancer
provided trace IDs).
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Callable

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
